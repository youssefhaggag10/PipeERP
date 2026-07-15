from app.repositories.treasury_repository import TreasuryRepository
from app.services.payment_account_rules import (
    account_matches_payment_method,
    expected_account_label,
)


class StrictTreasuryRepository(TreasuryRepository):
    """Treasury repository with explicit compatible accounts and editable balances."""

    def __init__(self, database) -> None:
        super().__init__(database)
        self._ensure_adjustment_schema()
        self._skip_payment_balance_check = False

    def _ensure_adjustment_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_account_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adjustment_number TEXT NOT NULL UNIQUE,
                    adjustment_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    financial_account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    amount REAL NOT NULL,
                    target_balance REAL NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_financial_account_adjustments
                ON financial_account_adjustments(financial_account_id, adjustment_date, id)
                """
            )

    def account_balance(self, account_id: int) -> float:
        if self._skip_payment_balance_check:
            return float("inf")
        return super().account_balance(account_id)

    def list_financial_accounts(self, *, active_only: bool = True) -> list[dict]:
        rows = super().list_financial_accounts(active_only=active_only)
        adjustment_rows = self.database.fetch_all(
            """
            SELECT financial_account_id, COALESCE(SUM(amount), 0) AS adjustment_total
            FROM financial_account_adjustments
            GROUP BY financial_account_id
            """
        )
        adjustments = {
            int(row["financial_account_id"]): float(row["adjustment_total"])
            for row in adjustment_rows
        }
        for row in rows:
            row["current_balance"] = (
                float(row["current_balance"]) + adjustments.get(int(row["id"]), 0.0)
            )
        return rows

    def update_financial_account(
        self,
        account_id: int,
        *,
        code: str,
        name: str,
        account_type: str,
        notes: str = "",
    ) -> None:
        code = code.strip().upper()
        name = name.strip()
        if not code or not name:
            raise ValueError("كود واسم الحساب مطلوبان")
        if account_type not in {"cash", "bank", "wallet", "other"}:
            raise ValueError("نوع الحساب غير صحيح")
        with self.database.session(immediate=True) as connection:
            existing = connection.execute(
                "SELECT id FROM financial_accounts WHERE id = ? AND is_active = 1",
                (int(account_id),),
            ).fetchone()
            if existing is None:
                raise ValueError("الحساب المالي غير موجود أو غير نشط")
            duplicate = connection.execute(
                "SELECT id FROM financial_accounts WHERE code = ? AND id <> ?",
                (code, int(account_id)),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("كود الحساب مستخدم في حساب آخر")
            connection.execute(
                """
                UPDATE financial_accounts
                SET code = ?, name = ?, account_type = ?, notes = ?
                WHERE id = ?
                """,
                (code, name, account_type, notes.strip(), int(account_id)),
            )

    def adjust_financial_account_balance(
        self,
        account_id: int,
        *,
        target_balance: float,
        notes: str,
    ) -> int:
        notes = notes.strip()
        if not notes:
            raise ValueError("سبب التسوية مطلوب")
        current_balance = self.account_balance(int(account_id))
        difference = float(target_balance) - float(current_balance)
        if abs(difference) <= 0.000001:
            raise ValueError("الرصيد الحالي يساوي الرصيد المطلوب؛ لا توجد تسوية")
        with self.database.session(immediate=True) as connection:
            account = connection.execute(
                "SELECT id FROM financial_accounts WHERE id = ? AND is_active = 1",
                (int(account_id),),
            ).fetchone()
            if account is None:
                raise ValueError("الحساب المالي غير موجود أو غير نشط")
            next_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM financial_account_adjustments"
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO financial_account_adjustments(
                    adjustment_number, financial_account_id, amount, target_balance, notes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"ADJ-FIN-{next_id:06d}",
                    int(account_id),
                    difference,
                    float(target_balance),
                    notes,
                ),
            )
            return int(cursor.lastrowid)

    def list_account_movements(self, limit: int = 1000) -> list[dict]:
        rows = super().list_account_movements(limit)
        adjustment_rows = self.database.fetch_all(
            """
            SELECT a.adjustment_date AS movement_date,
                   a.adjustment_number AS movement_number,
                   fa.name AS account_name,
                   'تسوية رصيد' AS movement_type,
                   CASE WHEN a.amount > 0 THEN a.amount ELSE 0 END AS amount_in,
                   CASE WHEN a.amount < 0 THEN ABS(a.amount) ELSE 0 END AS amount_out,
                   'تسوية داخلية' AS counterparty,
                   a.notes || ' — الرصيد بعد التسوية: ' || printf('%.2f', a.target_balance) AS notes
            FROM financial_account_adjustments a
            JOIN financial_accounts fa ON fa.id = a.financial_account_id
            ORDER BY a.adjustment_date DESC, a.id DESC
            """
        )
        rows.extend(dict(row) for row in adjustment_rows)
        rows.sort(
            key=lambda row: (str(row.get("movement_date", "")), str(row.get("movement_number", ""))),
            reverse=True,
        )
        return rows[:limit]

    def record_payment(
        self,
        *,
        transaction_type: str,
        partner_id: int,
        amount: float,
        payment_method: str = "نقدي",
        reference_id: int | None = None,
        notes: str = "",
        financial_account_id: int | None = None,
    ) -> int:
        if financial_account_id is None:
            raise ValueError("اختر حساب الخزينة أو البنك المستخدم في الحركة")

        account = self.database.fetch_one(
            """
            SELECT id, account_type
            FROM financial_accounts
            WHERE id = ? AND is_active = 1
            """,
            (int(financial_account_id),),
        )
        if account is None:
            raise ValueError("حساب الخزينة أو البنك غير موجود أو غير نشط")
        if not account_matches_payment_method(payment_method, str(account["account_type"])):
            raise ValueError(
                f"طريقة الدفع «{payment_method}» تتطلب {expected_account_label(payment_method)}"
            )

        self._skip_payment_balance_check = True
        try:
            return super().record_payment(
                transaction_type=transaction_type,
                partner_id=partner_id,
                amount=amount,
                payment_method=payment_method,
                reference_id=reference_id,
                notes=notes,
                financial_account_id=int(financial_account_id),
            )
        finally:
            self._skip_payment_balance_check = False


__all__ = ["StrictTreasuryRepository"]
