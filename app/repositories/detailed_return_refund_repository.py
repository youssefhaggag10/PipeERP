from app.repositories.return_refund_repository import ReturnRefundRepository


class DetailedReturnRefundRepository(ReturnRefundRepository):
    """Provides drill-down rows for every account summary card."""

    def summary_card_details(self, key: str) -> dict:
        if key in {"sales_total", "purchases_total"}:
            return self._invoice_details(key)
        if key in {"customer_receipts", "supplier_payments"}:
            return self._payment_details(key)
        if key in {"customer_advances", "supplier_advances"}:
            return self._advance_details(key)
        if key in {"receivables", "payables"}:
            return self._balance_details(key)
        raise ValueError("نوع تفاصيل الكارت غير معروف")

    def _invoice_details(self, key: str) -> dict:
        is_sales = key == "sales_total"
        invoice_table = "sales_invoices" if is_sales else "purchase_invoices"
        order_table = "sales_orders" if is_sales else "purchase_orders"
        order_fk = "sales_order_id" if is_sales else "purchase_order_id"
        partner_fk = "customer_id" if is_sales else "supplier_id"
        invoice_type = "sales" if is_sales else "purchase"
        title = "تفاصيل إجمالي فواتير المبيعات" if is_sales else "تفاصيل إجمالي فواتير المشتريات"
        rows = self.database.fetch_all(
            f"""
            SELECT invoice.invoice_number, orders.order_number, p.name AS partner_name,
                   invoice.invoice_date, invoice.total AS original_total,
                   COALESCE((
                       SELECT SUM(ir.total) FROM invoice_returns ir
                       WHERE ir.invoice_type = ? AND ir.invoice_id = invoice.id
                   ), 0) AS returned_total,
                   invoice.total - COALESCE((
                       SELECT SUM(ir.total) FROM invoice_returns ir
                       WHERE ir.invoice_type = ? AND ir.invoice_id = invoice.id
                   ), 0) AS net_total
            FROM {invoice_table} invoice
            JOIN {order_table} orders ON orders.id = invoice.{order_fk}
            JOIN partners p ON p.id = invoice.{partner_fk}
            WHERE invoice.status = 'posted'
            ORDER BY invoice.id DESC
            """,
            (invoice_type, invoice_type),
        )
        data = [
            [
                row["invoice_number"], row["order_number"], row["partner_name"],
                row["invoice_date"], f"{float(row['original_total']):,.2f}",
                f"{float(row['returned_total']):,.2f}", f"{float(row['net_total']):,.2f}",
            ]
            for row in rows
        ]
        return {
            "title": title,
            "headers": ["الفاتورة", "الأمر", "الطرف", "التاريخ", "الأصلي", "المرتجع", "الصافي"],
            "rows": data,
        }

    def _payment_details(self, key: str) -> dict:
        is_customer = key == "customer_receipts"
        transaction_type = "customer_receipt" if is_customer else "supplier_payment"
        title = "تفاصيل تحصيلات العملاء" if is_customer else "تفاصيل مدفوعات الموردين"
        rows = self.database.fetch_all(
            """
            SELECT pt.transaction_number, pt.transaction_date, p.name AS partner_name,
                   pt.amount, COALESCE(pt.payment_method, '') AS payment_method,
                   COALESCE(fa.name, '-') AS account_name,
                   CASE
                     WHEN pt.reference_type = 'sale' THEN
                       COALESCE((SELECT invoice_number FROM sales_invoices WHERE sales_order_id = pt.reference_id),
                                (SELECT order_number FROM sales_orders WHERE id = pt.reference_id), '-')
                     WHEN pt.reference_type = 'purchase' THEN
                       COALESCE((SELECT invoice_number FROM purchase_invoices WHERE purchase_order_id = pt.reference_id),
                                (SELECT order_number FROM purchase_orders WHERE id = pt.reference_id), '-')
                     ELSE '-'
                   END AS reference_number,
                   COALESCE(pt.notes, '') AS notes
            FROM payment_transactions pt
            JOIN partners p ON p.id = pt.partner_id
            LEFT JOIN financial_accounts fa ON fa.id = pt.financial_account_id
            WHERE pt.transaction_type = ?
            ORDER BY pt.id DESC
            """,
            (transaction_type,),
        )
        data = [
            [
                row["transaction_number"], row["transaction_date"], row["partner_name"],
                f"{float(row['amount']):,.2f}", row["payment_method"], row["account_name"],
                row["reference_number"], row["notes"],
            ]
            for row in rows
        ]
        return {
            "title": title,
            "headers": ["رقم الحركة", "التاريخ", "الطرف", "المبلغ", "الطريقة", "الحساب", "المستند", "ملاحظات"],
            "rows": data,
        }

    def _advance_details(self, key: str) -> dict:
        is_customer = key == "customer_advances"
        transaction_type = "customer_receipt" if is_customer else "supplier_payment"
        reference_type = "sale" if is_customer else "purchase"
        invoice_table = "sales_invoices" if is_customer else "purchase_invoices"
        invoice_order_fk = "sales_order_id" if is_customer else "purchase_order_id"
        title = "تفاصيل الدفعات المقدمة من العملاء" if is_customer else "تفاصيل الدفعات المقدمة للموردين"
        rows = self.database.fetch_all(
            f"""
            SELECT pt.transaction_number, pt.transaction_date, p.name AS partner_name,
                   pt.amount, COALESCE(pt.payment_method, '') AS payment_method,
                   COALESCE(fa.name, '-') AS account_name,
                   CASE
                     WHEN pt.reference_id IS NULL THEN 'بدون مستند'
                     WHEN pt.reference_type = 'sale' THEN COALESCE((SELECT order_number FROM sales_orders WHERE id = pt.reference_id), '-')
                     WHEN pt.reference_type = 'purchase' THEN COALESCE((SELECT order_number FROM purchase_orders WHERE id = pt.reference_id), '-')
                     ELSE '-'
                   END AS reference_number,
                   COALESCE(pt.notes, '') AS notes
            FROM payment_transactions pt
            JOIN partners p ON p.id = pt.partner_id
            LEFT JOIN financial_accounts fa ON fa.id = pt.financial_account_id
            WHERE pt.transaction_type = ?
              AND (
                  pt.reference_id IS NULL
                  OR (
                      pt.reference_type = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM {invoice_table} invoice
                          WHERE invoice.{invoice_order_fk} = pt.reference_id
                            AND invoice.status = 'posted'
                      )
                  )
              )
            ORDER BY pt.id DESC
            """,
            (transaction_type, reference_type),
        )
        data = [
            [
                row["transaction_number"], row["transaction_date"], row["partner_name"],
                f"{float(row['amount']):,.2f}", row["payment_method"], row["account_name"],
                row["reference_number"], row["notes"],
            ]
            for row in rows
        ]
        return {
            "title": title,
            "headers": ["رقم الحركة", "التاريخ", "الطرف", "المبلغ", "الطريقة", "الحساب", "المستند", "ملاحظات"],
            "rows": data,
        }

    def _balance_details(self, key: str) -> dict:
        partner_type = "customer" if key == "receivables" else "supplier"
        title = "تفاصيل مديونيات العملاء" if partner_type == "customer" else "تفاصيل مديونيات الموردين"
        rows = self.list_partner_balances(partner_type)
        data = [
            [
                row["code"], row["name"], f"{float(row['opening_balance']):,.2f}",
                f"{float(row['invoices_total']):,.2f}", f"{float(row['paid']):,.2f}",
                f"{float(row['advances']):,.2f}", f"{float(row.get('refunds_total', 0)) :,.2f}",
                f"{float(row['balance']):,.2f}",
            ]
            for row in rows
        ]
        return {
            "title": title,
            "headers": ["الكود", "الطرف", "افتتاحي", "صافي الفواتير", "سداد فواتير", "دفعات مقدمة", "استردادات", "الرصيد"],
            "rows": data,
        }


__all__ = ["DetailedReturnRefundRepository"]
