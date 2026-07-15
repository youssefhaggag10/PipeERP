from app.repositories.treasury_repository import EPSILON, TreasuryRepository
from app.services.payment_account_rules import (
    account_matches_payment_method,
    expected_account_label,
)


class StrictTreasuryRepository(TreasuryRepository):
    """Treasury repository that requires an explicit compatible account on every new payment."""

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

        if transaction_type == "supplier_payment":
            if self.account_balance(int(financial_account_id)) + EPSILON < float(amount):
                raise ValueError("رصيد حساب السداد غير كافٍ")

        return super().record_payment(
            transaction_type=transaction_type,
            partner_id=partner_id,
            amount=amount,
            payment_method=payment_method,
            reference_id=reference_id,
            notes=notes,
            financial_account_id=int(financial_account_id),
        )


__all__ = ["StrictTreasuryRepository"]
