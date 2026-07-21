from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.repositories.detailed_return_refund_repository import (
    DetailedReturnRefundRepository,
)
from app.services.payment_account_rules import (
    account_matches_payment_method,
    expected_account_label,
)
from app.services.payment_service import post_order_payment

EPSILON = 0.000001


class CustomerStatementAccountingRepository(DetailedReturnRefundRepository):
    """Existing accounts repository plus invoice allocations and customer statements."""

    def list_open_sales_invoices(self, customer_id: int) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT si.id, si.invoice_number, si.invoice_date, si.invoice_type,
                   si.status, si.sales_order_id, so.order_number,
                   CASE WHEN ABS(COALESCE(si.net_total, 0)) > 0.0000001
                        THEN si.net_total ELSE si.total END AS invoice_total,
                   COALESCE((
                       SELECT SUM(ir.total) FROM invoice_returns ir
                       WHERE ir.invoice_type = 'sales' AND ir.invoice_id = si.id
                   ), 0) AS returned_total,
                   COALESCE((
                       SELECT SUM(pa.amount) FROM payment_allocations pa
                       WHERE pa.sales_invoice_id = si.id
                   ), 0) AS allocated_paid,
                   COALESCE((
                       SELECT SUM(rr.amount) FROM return_refunds rr
                       WHERE rr.refund_type = 'customer_refund'
                         AND rr.invoice_type = 'sales' AND rr.invoice_id = si.id
                   ), 0) AS cash_refunded
            FROM sales_invoices si
            JOIN sales_orders so ON so.id = si.sales_order_id
            WHERE si.customer_id = ? AND si.status = 'posted'
            ORDER BY si.invoice_date, si.id
            """,
            (int(customer_id),),
        )
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            net_invoice = max(
                0.0,
                float(item["invoice_total"]) - float(item["returned_total"]),
            )
            effective_paid = max(
                0.0,
                float(item["allocated_paid"]) - float(item["cash_refunded"]),
            )
            item["net_invoice_total"] = net_invoice
            item["paid"] = effective_paid
            item["remaining"] = max(0.0, net_invoice - effective_paid)
            if item["remaining"] > EPSILON:
                result.append(item)
        return result

    def record_customer_receipt_allocated(
        self,
        *,
        customer_id: int,
        amount: float,
        payment_method: str,
        financial_account_id: int,
        allocations: list[dict] | None = None,
        notes: str = "",
    ) -> int:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        account = self.database.fetch_one(
            """
            SELECT id, account_type FROM financial_accounts
            WHERE id = ? AND is_active = 1
            """,
            (int(financial_account_id),),
        )
        if account is None:
            raise ValueError("حساب الخزينة أو البنك غير موجود أو غير نشط")
        if not account_matches_payment_method(payment_method, str(account["account_type"])):
            raise ValueError(
                f"طريقة الدفع «{payment_method}» تتطلب "
                f"{expected_account_label(payment_method)}"
            )

        merged: dict[int, float] = defaultdict(float)
        for allocation in allocations or []:
            invoice_id = int(allocation["sales_invoice_id"])
            allocated_amount = float(allocation["amount"])
            if allocated_amount <= EPSILON:
                continue
            merged[invoice_id] += allocated_amount
        allocated_total = sum(merged.values())
        if allocated_total - amount > EPSILON:
            raise ValueError("إجمالي توزيع التحصيل أكبر من مبلغ التحصيل")

        open_invoices = {
            int(row["id"]): row for row in self.list_open_sales_invoices(int(customer_id))
        }
        for invoice_id, allocated_amount in merged.items():
            invoice = open_invoices.get(invoice_id)
            if invoice is None:
                raise ValueError("إحدى الفواتير لا تخص العميل أو ليس عليها متبقي")
            if allocated_amount - float(invoice["remaining"]) > EPSILON:
                raise ValueError(
                    f"التوزيع على الفاتورة {invoice['invoice_number']} أكبر من المتبقي "
                    f"({float(invoice['remaining']):,.2f})"
                )

        with self.database.session(immediate=True) as connection:
            customer = connection.execute(
                """
                SELECT id FROM partners
                WHERE id = ? AND partner_type = 'customer' AND is_active = 1
                """,
                (int(customer_id),),
            ).fetchone()
            if customer is None:
                raise ValueError("العميل غير موجود أو غير نشط")
            reference_id = None
            if len(merged) == 1 and abs(allocated_total - amount) <= EPSILON:
                only_invoice_id = next(iter(merged))
                reference_id = int(open_invoices[only_invoice_id]["sales_order_id"])
            transaction_id = post_order_payment(
                connection,
                transaction_type="customer_receipt",
                partner_id=int(customer_id),
                amount=amount,
                reference_type="sale" if reference_id is not None else None,
                reference_id=reference_id,
                notes=notes,
                payment_method=payment_method,
                financial_account_id=int(financial_account_id),
            )
            for invoice_id, allocated_amount in merged.items():
                connection.execute(
                    """
                    INSERT INTO payment_allocations(
                        transaction_id, sales_invoice_id, amount
                    ) VALUES (?, ?, ?)
                    """,
                    (transaction_id, invoice_id, allocated_amount),
                )
            if len(merged) == 1 and abs(allocated_total - amount) <= EPSILON:
                connection.execute(
                    "UPDATE payment_transactions SET sales_invoice_id = ? WHERE id = ?",
                    (next(iter(merged)), transaction_id),
                )
            return transaction_id

    def record_payment(self, **kwargs) -> int:
        transaction_type = str(kwargs.get("transaction_type"))
        if transaction_type != "customer_receipt":
            return super().record_payment(**kwargs)
        reference_id = kwargs.get("reference_id")
        allocations: list[dict] = []
        if reference_id is not None:
            invoice = self.database.fetch_one(
                """
                SELECT id FROM sales_invoices
                WHERE sales_order_id = ? AND customer_id = ? AND status = 'posted'
                """,
                (int(reference_id), int(kwargs["partner_id"])),
            )
            if invoice is not None:
                allocations.append(
                    {
                        "sales_invoice_id": int(invoice["id"]),
                        "amount": float(kwargs["amount"]),
                    }
                )
        return self.record_customer_receipt_allocated(
            customer_id=int(kwargs["partner_id"]),
            amount=float(kwargs["amount"]),
            payment_method=str(kwargs.get("payment_method") or "نقدي"),
            financial_account_id=int(kwargs["financial_account_id"]),
            allocations=allocations,
            notes=str(kwargs.get("notes") or ""),
        )

    def get_customer_statement(
        self,
        *,
        customer_id: int,
        date_from: date,
        date_to: date,
        include_drafts: bool = False,
        detailed: bool = False,
    ) -> dict:
        if date_from > date_to:
            raise ValueError("تاريخ البداية يجب ألا يكون بعد تاريخ النهاية")
        customer = self.database.fetch_one(
            """
            SELECT id, code, name, phone, address, opening_balance
            FROM partners
            WHERE id = ? AND partner_type = 'customer'
            """,
            (int(customer_id),),
        )
        if customer is None:
            raise ValueError("العميل غير موجود")
        start = date_from.isoformat()
        end = date_to.isoformat() + " 23:59:59"
        opening_balance = float(customer["opening_balance"] or 0)
        opening_balance += self._movement_balance_before(int(customer_id), start)

        movements: list[dict] = []
        invoice_rows = self.database.fetch_all(
            """
            SELECT si.id, si.invoice_number AS document_number,
                   si.invoice_date AS movement_date, si.invoice_type,
                   si.status, so.order_number,
                   CASE WHEN ABS(COALESCE(si.net_total, 0)) > 0.0000001
                        THEN si.net_total ELSE si.total END AS amount
            FROM sales_invoices si
            JOIN sales_orders so ON so.id = si.sales_order_id
            WHERE si.customer_id = ? AND si.status = 'posted'
              AND si.invoice_date BETWEEN ? AND ?
            ORDER BY si.invoice_date, si.id
            """,
            (int(customer_id), start, end),
        )
        for sequence, row in enumerate(invoice_rows):
            invoice_type = str(row["invoice_type"] or "standard")
            movement = {
                "movement_date": str(row["movement_date"]),
                "document_number": str(row["document_number"]),
                "document_type": (
                    "فاتورة بيع بالوزن" if invoice_type == "weight" else "فاتورة بيع عادية"
                ),
                "description": f"أمر البيع {row['order_number']}",
                "debit": float(row["amount"] or 0),
                "credit": 0.0,
                "status": "معتمد",
                "invoice_id": int(row["id"]),
                "invoice_type": invoice_type,
                "sort_order": (str(row["movement_date"]), 10, sequence),
            }
            if detailed:
                movement["lines"] = self._statement_invoice_lines(
                    int(row["id"]), invoice_type
                )
            movements.append(movement)

        return_rows = self.database.fetch_all(
            """
            SELECT ir.id, ir.return_number AS document_number,
                   ir.return_date AS movement_date, ir.total AS amount,
                   ir.reason, si.invoice_number
            FROM invoice_returns ir
            JOIN sales_invoices si ON si.id = ir.invoice_id
            WHERE ir.invoice_type = 'sales' AND si.customer_id = ?
              AND ir.return_date BETWEEN ? AND ?
            ORDER BY ir.return_date, ir.id
            """,
            (int(customer_id), start, end),
        )
        for sequence, row in enumerate(return_rows):
            movements.append(
                {
                    "movement_date": str(row["movement_date"]),
                    "document_number": str(row["document_number"]),
                    "document_type": "مرتجع مبيعات",
                    "description": f"فاتورة {row['invoice_number']} — {row['reason']}",
                    "debit": 0.0,
                    "credit": float(row["amount"] or 0),
                    "status": "معتمد",
                    "sort_order": (str(row["movement_date"]), 20, sequence),
                }
            )

        payment_rows = self.database.fetch_all(
            """
            SELECT id, transaction_number AS document_number,
                   transaction_date AS movement_date, amount,
                   payment_method, COALESCE(notes, '') AS notes
            FROM payment_transactions
            WHERE partner_id = ? AND transaction_type = 'customer_receipt'
              AND transaction_date BETWEEN ? AND ?
            ORDER BY transaction_date, id
            """,
            (int(customer_id), start, end),
        )
        for sequence, row in enumerate(payment_rows):
            movements.append(
                {
                    "movement_date": str(row["movement_date"]),
                    "document_number": str(row["document_number"]),
                    "document_type": "تحصيل عميل",
                    "description": (
                        f"{row['payment_method']}"
                        + (f" — {row['notes']}" if row["notes"] else "")
                    ),
                    "debit": 0.0,
                    "credit": float(row["amount"] or 0),
                    "status": "معتمد",
                    "transaction_id": int(row["id"]),
                    "sort_order": (str(row["movement_date"]), 30, sequence),
                }
            )

        refund_rows = self.database.fetch_all(
            """
            SELECT rr.id, rr.refund_number AS document_number,
                   rr.refund_date AS movement_date, rr.amount,
                   COALESCE(rr.notes, '') AS notes
            FROM return_refunds rr
            WHERE rr.partner_id = ? AND rr.refund_type = 'customer_refund'
              AND rr.refund_date BETWEEN ? AND ?
            ORDER BY rr.refund_date, rr.id
            """,
            (int(customer_id), start, end),
        )
        for sequence, row in enumerate(refund_rows):
            movements.append(
                {
                    "movement_date": str(row["movement_date"]),
                    "document_number": str(row["document_number"]),
                    "document_type": "رد مبلغ لعميل",
                    "description": str(row["notes"] or ""),
                    "debit": float(row["amount"] or 0),
                    "credit": 0.0,
                    "status": "معتمد",
                    "sort_order": (str(row["movement_date"]), 40, sequence),
                }
            )

        adjustment_rows = self.database.fetch_all(
            """
            SELECT id, adjustment_number AS document_number,
                   adjustment_date AS movement_date, adjustment_type,
                   amount, status, COALESCE(notes, '') AS notes
            FROM customer_account_adjustments
            WHERE customer_id = ? AND status = 'posted'
              AND adjustment_date BETWEEN ? AND ?
            ORDER BY adjustment_date, id
            """,
            (int(customer_id), start, end),
        )
        for sequence, row in enumerate(adjustment_rows):
            is_debit = str(row["adjustment_type"]) == "debit"
            movements.append(
                {
                    "movement_date": str(row["movement_date"]),
                    "document_number": str(row["document_number"]),
                    "document_type": "تسوية مدينة" if is_debit else "تسوية دائنة",
                    "description": str(row["notes"] or ""),
                    "debit": float(row["amount"] or 0) if is_debit else 0.0,
                    "credit": 0.0 if is_debit else float(row["amount"] or 0),
                    "status": "معتمد",
                    "sort_order": (str(row["movement_date"]), 50, sequence),
                }
            )

        if include_drafts:
            draft_rows = self.database.fetch_all(
                """
                SELECT so.id, so.order_number AS document_number,
                       so.order_date AS movement_date, so.billing_method,
                       COALESCE(SUM(sol.line_total), 0) AS amount
                FROM sales_orders so
                LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
                WHERE so.customer_id = ? AND so.status = 'draft'
                  AND so.order_date BETWEEN ? AND ?
                GROUP BY so.id
                ORDER BY so.order_date, so.id
                """,
                (int(customer_id), start, end),
            )
            for sequence, row in enumerate(draft_rows):
                movements.append(
                    {
                        "movement_date": str(row["movement_date"]),
                        "document_number": str(row["document_number"]),
                        "document_type": (
                            "مسودة بيع بالوزن"
                            if str(row["billing_method"]) == "weight"
                            else "مسودة بيع عادية"
                        ),
                        "description": f"للمراجعة فقط — قيمة {float(row['amount']):,.2f}",
                        "debit": 0.0,
                        "credit": 0.0,
                        "status": "مسودة — لا تدخل في الرصيد",
                        "sort_order": (str(row["movement_date"]), 90, sequence),
                    }
                )

        movements.sort(key=lambda item: item["sort_order"])
        running = opening_balance
        for movement in movements:
            running += float(movement["debit"]) - float(movement["credit"])
            movement["running_balance"] = running
            movement.pop("sort_order", None)

        standard_total = sum(
            float(item["debit"])
            for item in movements
            if item.get("invoice_type") == "standard"
        )
        weight_total = sum(
            float(item["debit"])
            for item in movements
            if item.get("invoice_type") == "weight"
        )
        returns_total = sum(
            float(item["credit"])
            for item in movements
            if item["document_type"] == "مرتجع مبيعات"
        )
        receipts_total = sum(
            float(item["credit"])
            for item in movements
            if item["document_type"] == "تحصيل عميل"
        )
        refunds_total = sum(
            float(item["debit"])
            for item in movements
            if item["document_type"] == "رد مبلغ لعميل"
        )
        adjustment_debit = sum(
            float(item["debit"])
            for item in movements
            if item["document_type"] == "تسوية مدينة"
        )
        adjustment_credit = sum(
            float(item["credit"])
            for item in movements
            if item["document_type"] == "تسوية دائنة"
        )
        net_movement = sum(
            float(item["debit"]) - float(item["credit"])
            for item in movements
        )
        return {
            "customer": dict(customer),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "detailed": bool(detailed),
            "include_drafts": bool(include_drafts),
            "opening_balance": opening_balance,
            "movements": movements,
            "summary": {
                "opening_balance": opening_balance,
                "standard_sales_total": standard_total,
                "weight_sales_total": weight_total,
                "returns_total": returns_total,
                "receipts_total": receipts_total,
                "customer_refunds_total": refunds_total,
                "adjustments_total": adjustment_debit - adjustment_credit,
                "net_movement": net_movement,
                "closing_balance": running,
            },
        }

    def _movement_balance_before(self, customer_id: int, start: str) -> float:
        row = self.database.fetch_one(
            """
            SELECT
                COALESCE((
                    SELECT SUM(CASE WHEN ABS(COALESCE(si.net_total, 0)) > 0.0000001
                                    THEN si.net_total ELSE si.total END)
                    FROM sales_invoices si
                    WHERE si.customer_id = ? AND si.status = 'posted'
                      AND si.invoice_date < ?
                ), 0)
                - COALESCE((
                    SELECT SUM(ir.total)
                    FROM invoice_returns ir
                    JOIN sales_invoices si ON si.id = ir.invoice_id
                    WHERE ir.invoice_type = 'sales' AND si.customer_id = ?
                      AND ir.return_date < ?
                ), 0)
                - COALESCE((
                    SELECT SUM(pt.amount) FROM payment_transactions pt
                    WHERE pt.partner_id = ?
                      AND pt.transaction_type = 'customer_receipt'
                      AND pt.transaction_date < ?
                ), 0)
                + COALESCE((
                    SELECT SUM(rr.amount) FROM return_refunds rr
                    WHERE rr.partner_id = ? AND rr.refund_type = 'customer_refund'
                      AND rr.refund_date < ?
                ), 0)
                + COALESCE((
                    SELECT SUM(CASE WHEN caa.adjustment_type = 'debit'
                                    THEN caa.amount ELSE -caa.amount END)
                    FROM customer_account_adjustments caa
                    WHERE caa.customer_id = ? AND caa.status = 'posted'
                      AND caa.adjustment_date < ?
                ), 0) AS balance
            """,
            (
                customer_id,
                start,
                customer_id,
                start,
                customer_id,
                start,
                customer_id,
                start,
                customer_id,
                start,
            ),
        )
        return float(row["balance"] if row is not None else 0)

    def _statement_invoice_lines(self, invoice_id: int, invoice_type: str) -> list[dict]:
        if invoice_type == "weight":
            rows = self.database.fetch_all(
                """
                SELECT p.code, p.name AS description, sol.unit,
                       wcl.quantity_pieces AS quantity,
                       wcl.actual_weight_kg, wcl.price_per_kg,
                       wcl.line_total, wcl.notes
                FROM sales_invoices si
                JOIN sales_weight_cards wc ON wc.sales_invoice_id = si.id
                JOIN sales_weight_card_lines wcl ON wcl.weight_card_id = wc.id
                JOIN sales_order_lines sol ON sol.id = wcl.sales_order_line_id
                JOIN products p ON p.id = wcl.product_id
                WHERE si.id = ? ORDER BY wcl.id
                """,
                (int(invoice_id),),
            )
        else:
            rows = self.database.fetch_all(
                """
                SELECT p.code, p.name AS description, sol.unit, sol.quantity,
                       NULL AS actual_weight_kg, NULL AS price_per_kg,
                       sol.unit_price, sol.line_total, '' AS notes
                FROM sales_invoices si
                JOIN sales_order_lines sol ON sol.sales_order_id = si.sales_order_id
                JOIN products p ON p.id = sol.product_id
                WHERE si.id = ? ORDER BY sol.id
                """,
                (int(invoice_id),),
            )
        return [dict(row) for row in rows]


__all__ = ["CustomerStatementAccountingRepository"]
