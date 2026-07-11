from datetime import date

from app.database.connection import Database
from app.services.payment_service import post_order_payment


class AccountingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def dashboard_summary(self) -> dict:
        row = self.database.fetch_one(
            """
            SELECT
                COALESCE((SELECT SUM(line_total) FROM sales_order_lines), 0) AS sales_total,
                COALESCE((SELECT SUM(line_total) FROM purchase_order_lines), 0) AS purchases_total,
                COALESCE((
                    SELECT SUM(amount) FROM payment_transactions
                    WHERE transaction_type = 'customer_receipt'
                ), 0) AS customer_receipts,
                COALESCE((
                    SELECT SUM(amount) FROM payment_transactions
                    WHERE transaction_type = 'supplier_payment'
                ), 0) AS supplier_payments,
                COALESCE((
                    SELECT SUM(opening_balance) FROM partners
                    WHERE partner_type = 'customer' AND is_active = 1
                ), 0) AS customer_opening,
                COALESCE((
                    SELECT SUM(opening_balance) FROM partners
                    WHERE partner_type = 'supplier' AND is_active = 1
                ), 0) AS supplier_opening
            """
        )
        result = dict(row or {})
        result["receivables"] = (
            float(result.get("sales_total", 0))
            + float(result.get("customer_opening", 0))
            - float(result.get("customer_receipts", 0))
        )
        result["payables"] = (
            float(result.get("purchases_total", 0))
            + float(result.get("supplier_opening", 0))
            - float(result.get("supplier_payments", 0))
        )
        return result

    def list_partner_balances(self, partner_type: str) -> list[dict]:
        if partner_type not in {"customer", "supplier"}:
            raise ValueError("نوع الطرف غير صحيح")
        if partner_type == "customer":
            order_table = "sales_orders"
            line_table = "sales_order_lines"
            order_fk = "sales_order_id"
            partner_fk = "customer_id"
            payment_type = "customer_receipt"
        else:
            order_table = "purchase_orders"
            line_table = "purchase_order_lines"
            order_fk = "purchase_order_id"
            partner_fk = "supplier_id"
            payment_type = "supplier_payment"

        rows = self.database.fetch_all(
            f"""
            SELECT p.id, p.code, p.name, p.phone, p.opening_balance,
                   COALESCE((
                       SELECT SUM(lines.line_total)
                       FROM {order_table} orders_table
                       JOIN {line_table} lines ON lines.{order_fk} = orders_table.id
                       WHERE orders_table.{partner_fk} = p.id
                   ), 0) AS orders_total,
                   COALESCE((
                       SELECT SUM(pt.amount)
                       FROM payment_transactions pt
                       WHERE pt.partner_id = p.id
                         AND pt.transaction_type = ?
                   ), 0) AS paid
            FROM partners p
            WHERE p.partner_type = ? AND p.is_active = 1
            ORDER BY p.name
            """,
            (payment_type, partner_type),
        )
        result = []
        for row in rows:
            item = dict(row)
            item["balance"] = (
                float(item["opening_balance"])
                + float(item["orders_total"])
                - float(item["paid"])
            )
            result.append(item)
        return result

    def list_open_orders(self, partner_type: str, partner_id: int | None = None) -> list[dict]:
        if partner_type == "customer":
            rows = self.database.fetch_all(
                """
                SELECT so.id, so.order_number, so.customer_id AS partner_id,
                       COALESCE(SUM(sol.line_total), 0) AS total,
                       COALESCE((
                           SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id
                       ), 0) AS paid
                FROM sales_orders so
                LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
                WHERE (? IS NULL OR so.customer_id = ?)
                GROUP BY so.id, so.order_number, so.customer_id
                HAVING total - paid > 0.000001
                ORDER BY so.id DESC
                """,
                (partner_id, partner_id),
            )
        elif partner_type == "supplier":
            rows = self.database.fetch_all(
                """
                SELECT po.id, po.order_number, po.supplier_id AS partner_id,
                       COALESCE(SUM(pol.line_total), 0) AS total,
                       COALESCE((
                           SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.reference_type = 'purchase' AND pt.reference_id = po.id
                       ), 0) AS paid
                FROM purchase_orders po
                LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
                WHERE (? IS NULL OR po.supplier_id = ?)
                GROUP BY po.id, po.order_number, po.supplier_id
                HAVING total - paid > 0.000001
                ORDER BY po.id DESC
                """,
                (partner_id, partner_id),
            )
        else:
            raise ValueError("نوع الطرف غير صحيح")
        result = []
        for row in rows:
            item = dict(row)
            item["remaining"] = float(item["total"]) - float(item["paid"])
            result.append(item)
        return result

    def record_payment(
        self,
        *,
        transaction_type: str,
        partner_id: int,
        amount: float,
        payment_method: str = "cash",
        reference_id: int | None = None,
        notes: str = "",
    ) -> int:
        expected_partner_type = (
            "customer" if transaction_type == "customer_receipt" else "supplier"
        )
        if transaction_type not in {"customer_receipt", "supplier_payment"}:
            raise ValueError("نوع الحركة المالية غير صحيح")
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")

        with self.database.session(immediate=True) as connection:
            partner = connection.execute(
                """
                SELECT id FROM partners
                WHERE id = ? AND partner_type = ? AND is_active = 1
                """,
                (partner_id, expected_partner_type),
            ).fetchone()
            if partner is None:
                raise ValueError("العميل أو المورد غير موجود")

            reference_type = None
            if reference_id is not None:
                reference_type = "sale" if expected_partner_type == "customer" else "purchase"
                if reference_type == "sale":
                    order = connection.execute(
                        """
                        SELECT so.customer_id AS partner_id,
                               COALESCE(SUM(sol.line_total), 0) AS total,
                               COALESCE((
                                   SELECT SUM(pt.amount) FROM payment_transactions pt
                                   WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id
                               ), 0) AS paid
                        FROM sales_orders so
                        LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
                        WHERE so.id = ?
                        GROUP BY so.id, so.customer_id
                        """,
                        (reference_id,),
                    ).fetchone()
                else:
                    order = connection.execute(
                        """
                        SELECT po.supplier_id AS partner_id,
                               COALESCE(SUM(pol.line_total), 0) AS total,
                               COALESCE((
                                   SELECT SUM(pt.amount) FROM payment_transactions pt
                                   WHERE pt.reference_type = 'purchase' AND pt.reference_id = po.id
                               ), 0) AS paid
                        FROM purchase_orders po
                        LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
                        WHERE po.id = ?
                        GROUP BY po.id, po.supplier_id
                        """,
                        (reference_id,),
                    ).fetchone()
                if order is None or int(order["partner_id"]) != partner_id:
                    raise ValueError("المستند لا يخص الطرف المحدد")
                remaining = float(order["total"]) - float(order["paid"])
                if amount - remaining > 0.000001:
                    raise ValueError(f"المبلغ أكبر من المتبقي على المستند ({remaining:,.2f})")

            transaction_id = post_order_payment(
                connection,
                transaction_type=transaction_type,
                partner_id=partner_id,
                amount=amount,
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes,
            )
            connection.execute(
                "UPDATE payment_transactions SET payment_method = ? WHERE id = ?",
                (payment_method.strip() or "cash", transaction_id),
            )
            return transaction_id

    def list_transactions(self, limit: int = 500) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT pt.id, pt.transaction_number, pt.transaction_date,
                   pt.transaction_type, p.name AS partner_name, pt.amount,
                   pt.payment_method, pt.reference_type, pt.reference_id,
                   COALESCE(pt.notes, '') AS notes,
                   CASE
                       WHEN pt.reference_type = 'sale' THEN (
                           SELECT order_number FROM sales_orders WHERE id = pt.reference_id
                       )
                       WHEN pt.reference_type = 'purchase' THEN (
                           SELECT order_number FROM purchase_orders WHERE id = pt.reference_id
                       )
                       ELSE ''
                   END AS reference_number
            FROM payment_transactions pt
            JOIN partners p ON p.id = pt.partner_id
            ORDER BY pt.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows]

    def generate_report(
        self,
        report_key: str,
        *,
        date_from: date,
        date_to: date,
        partner_id: int | None = None,
    ) -> tuple[list[str], list[dict]]:
        start = date_from.isoformat()
        end = date_to.isoformat() + " 23:59:59"

        if report_key == "sales":
            columns = [
                "رقم الأمر", "التاريخ", "العميل", "الإجمالي", "المدفوع", "المتبقي", "الحالة"
            ]
            rows = self.database.fetch_all(
                """
                SELECT so.order_number AS 'رقم الأمر', so.order_date AS 'التاريخ',
                       p.name AS 'العميل', COALESCE(SUM(sol.line_total), 0) AS 'الإجمالي',
                       COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id), 0)
                           AS 'المدفوع',
                       COALESCE(SUM(sol.line_total), 0) - COALESCE((
                           SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id
                       ), 0) AS 'المتبقي', so.status AS 'الحالة'
                FROM sales_orders so
                JOIN partners p ON p.id = so.customer_id
                LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
                WHERE so.order_date BETWEEN ? AND ?
                  AND (? IS NULL OR so.customer_id = ?)
                GROUP BY so.id, so.order_number, so.order_date, p.name, so.status
                ORDER BY so.order_date DESC, so.id DESC
                """,
                (start, end, partner_id, partner_id),
            )
        elif report_key == "purchases":
            columns = [
                "رقم الأمر", "التاريخ", "المورد", "الإجمالي", "المدفوع", "المتبقي", "الحالة"
            ]
            rows = self.database.fetch_all(
                """
                SELECT po.order_number AS 'رقم الأمر', po.order_date AS 'التاريخ',
                       p.name AS 'المورد', COALESCE(SUM(pol.line_total), 0) AS 'الإجمالي',
                       COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.reference_type = 'purchase' AND pt.reference_id = po.id), 0)
                           AS 'المدفوع',
                       COALESCE(SUM(pol.line_total), 0) - COALESCE((
                           SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.reference_type = 'purchase' AND pt.reference_id = po.id
                       ), 0) AS 'المتبقي', po.status AS 'الحالة'
                FROM purchase_orders po
                JOIN partners p ON p.id = po.supplier_id
                LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
                WHERE po.order_date BETWEEN ? AND ?
                  AND (? IS NULL OR po.supplier_id = ?)
                GROUP BY po.id, po.order_number, po.order_date, p.name, po.status
                ORDER BY po.order_date DESC, po.id DESC
                """,
                (start, end, partner_id, partner_id),
            )
        elif report_key in {"customer_balances", "supplier_balances"}:
            partner_type = "customer" if report_key == "customer_balances" else "supplier"
            name_label = "العميل" if partner_type == "customer" else "المورد"
            columns = [name_label, "الرصيد الافتتاحي", "إجمالي المستندات", "المدفوع", "الرصيد"]
            balance_rows = self.list_partner_balances(partner_type)
            return columns, [
                {
                    name_label: item["name"],
                    "الرصيد الافتتاحي": item["opening_balance"],
                    "إجمالي المستندات": item["orders_total"],
                    "المدفوع": item["paid"],
                    "الرصيد": item["balance"],
                }
                for item in balance_rows
                if partner_id is None or int(item["id"]) == partner_id
            ]
        elif report_key == "payments":
            columns = ["رقم الحركة", "التاريخ", "النوع", "الطرف", "المبلغ", "الطريقة", "المستند", "ملاحظات"]
            rows = self.database.fetch_all(
                """
                SELECT pt.transaction_number AS 'رقم الحركة',
                       pt.transaction_date AS 'التاريخ',
                       CASE pt.transaction_type
                           WHEN 'customer_receipt' THEN 'تحصيل عميل'
                           ELSE 'سداد مورد'
                       END AS 'النوع', p.name AS 'الطرف', pt.amount AS 'المبلغ',
                       pt.payment_method AS 'الطريقة',
                       CASE
                           WHEN pt.reference_type = 'sale' THEN (
                               SELECT order_number FROM sales_orders WHERE id = pt.reference_id
                           )
                           WHEN pt.reference_type = 'purchase' THEN (
                               SELECT order_number FROM purchase_orders WHERE id = pt.reference_id
                           )
                           ELSE ''
                       END AS 'المستند', COALESCE(pt.notes, '') AS 'ملاحظات'
                FROM payment_transactions pt
                JOIN partners p ON p.id = pt.partner_id
                WHERE pt.transaction_date BETWEEN ? AND ?
                  AND (? IS NULL OR pt.partner_id = ?)
                ORDER BY pt.transaction_date DESC, pt.id DESC
                """,
                (start, end, partner_id, partner_id),
            )
        elif report_key == "inventory_valuation":
            columns = ["الكود", "الصنف", "الكمية", "متوسط التكلفة", "قيمة المخزون"]
            rows = self.database.fetch_all(
                """
                SELECT p.code AS 'الكود', p.name AS 'الصنف',
                       COALESCE(SUM(m.quantity_in - m.quantity_out), 0) AS 'الكمية',
                       CASE WHEN SUM(m.quantity_in - m.quantity_out) > 0
                            THEN SUM((m.quantity_in - m.quantity_out) * m.unit_cost)
                                 / SUM(m.quantity_in - m.quantity_out)
                            ELSE 0 END AS 'متوسط التكلفة',
                       COALESCE(SUM((m.quantity_in - m.quantity_out) * m.unit_cost), 0)
                           AS 'قيمة المخزون'
                FROM products p
                LEFT JOIN inventory_moves m ON m.product_id = p.id
                WHERE p.is_active = 1
                GROUP BY p.id, p.code, p.name
                ORDER BY p.name
                """
            )
        else:
            raise ValueError("نوع التقرير غير مدعوم")

        return columns, [dict(row) for row in rows]
