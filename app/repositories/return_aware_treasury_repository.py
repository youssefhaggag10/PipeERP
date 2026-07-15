from app.repositories.strict_treasury_repository import StrictTreasuryRepository


EPSILON = 0.000001


class ReturnAwareTreasuryRepository(StrictTreasuryRepository):
    """Operational accounting totals after deducting posted invoice returns."""

    def dashboard_summary(self) -> dict:
        result = super().dashboard_summary()
        rows = self.database.fetch_all(
            """
            SELECT invoice_type, COALESCE(SUM(total), 0) AS total
            FROM invoice_returns
            GROUP BY invoice_type
            """
        )
        returns = {str(row["invoice_type"]): float(row["total"]) for row in rows}
        sales_returns = returns.get("sales", 0.0)
        purchase_returns = returns.get("purchase", 0.0)
        result["sales_total"] = max(0.0, float(result.get("sales_total", 0)) - sales_returns)
        result["purchases_total"] = max(
            0.0, float(result.get("purchases_total", 0)) - purchase_returns
        )
        result["receivables"] = float(result.get("receivables", 0)) - sales_returns
        result["payables"] = float(result.get("payables", 0)) - purchase_returns
        return result

    def list_partner_balances(self, partner_type: str) -> list[dict]:
        rows = super().list_partner_balances(partner_type)
        if partner_type == "customer":
            invoice_table = "sales_invoices"
            partner_column = "customer_id"
            invoice_type = "sales"
        elif partner_type == "supplier":
            invoice_table = "purchase_invoices"
            partner_column = "supplier_id"
            invoice_type = "purchase"
        else:
            raise ValueError("نوع الطرف غير صحيح")

        return_rows = self.database.fetch_all(
            f"""
            SELECT invoice.{partner_column} AS partner_id,
                   COALESCE(SUM(ir.total), 0) AS returned_total
            FROM invoice_returns ir
            JOIN {invoice_table} invoice ON invoice.id = ir.invoice_id
            WHERE ir.invoice_type = ?
            GROUP BY invoice.{partner_column}
            """,
            (invoice_type,),
        )
        returned_by_partner = {
            int(row["partner_id"]): float(row["returned_total"]) for row in return_rows
        }
        for item in rows:
            returned = returned_by_partner.get(int(item["id"]), 0.0)
            item["returns_total"] = returned
            item["invoices_total"] = max(0.0, float(item["invoices_total"]) - returned)
            item["orders_total"] = item["invoices_total"]
            item["balance"] = (
                float(item["opening_balance"])
                + float(item["invoices_total"])
                - float(item["paid"])
            )
        return rows

    def list_open_orders(self, partner_type: str, partner_id: int | None = None) -> list[dict]:
        rows = super().list_open_orders(partner_type, partner_id)
        invoice_type = "sales" if partner_type == "customer" else "purchase"
        order_table = "sales_invoices" if partner_type == "customer" else "purchase_invoices"
        order_column = "sales_order_id" if partner_type == "customer" else "purchase_order_id"
        result: list[dict] = []
        for item in rows:
            returned_row = self.database.fetch_one(
                f"""
                SELECT COALESCE(SUM(ir.total), 0) AS total
                FROM invoice_returns ir
                JOIN {order_table} invoice ON invoice.id = ir.invoice_id
                WHERE ir.invoice_type = ? AND invoice.{order_column} = ?
                """,
                (invoice_type, int(item["id"])),
            )
            returned = float(returned_row["total"] if returned_row is not None else 0)
            item["returned_total"] = returned
            item["total"] = max(0.0, float(item["total"]) - returned)
            item["remaining"] = float(item["total"]) - float(item["paid"])
            if item["remaining"] > EPSILON:
                result.append(item)
        return result

    def record_payment(self, **kwargs) -> int:
        reference_id = kwargs.get("reference_id")
        if reference_id is not None:
            transaction_type = str(kwargs.get("transaction_type"))
            partner_type = "customer" if transaction_type == "customer_receipt" else "supplier"
            open_rows = self.list_open_orders(partner_type, int(kwargs.get("partner_id")))
            matching = next(
                (row for row in open_rows if int(row["id"]) == int(reference_id)),
                None,
            )
            amount = float(kwargs.get("amount", 0))
            if matching is None:
                raise ValueError("لا يوجد مبلغ متبقٍ على المستند بعد احتساب المرتجعات")
            if amount - float(matching["remaining"]) > EPSILON:
                raise ValueError(
                    f"المبلغ أكبر من صافي المتبقي بعد المرتجعات "
                    f"({float(matching['remaining']):,.2f})"
                )
        return super().record_payment(**kwargs)


__all__ = ["ReturnAwareTreasuryRepository"]
