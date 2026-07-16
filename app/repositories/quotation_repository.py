from __future__ import annotations

from app.database.connection import Database


class QuotationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.database.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sales_quotations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quotation_number TEXT NOT NULL UNIQUE,
                    customer_id INTEGER NOT NULL REFERENCES partners(id),
                    quotation_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    valid_until TEXT,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK(status IN ('draft', 'sent', 'accepted', 'rejected', 'cancelled')),
                    total REAL NOT NULL DEFAULT 0,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sales_quotation_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quotation_id INTEGER NOT NULL REFERENCES sales_quotations(id) ON DELETE CASCADE,
                    product_id INTEGER REFERENCES products(id),
                    item_name TEXT NOT NULL,
                    quantity REAL NOT NULL CHECK(quantity > 0),
                    unit TEXT NOT NULL,
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    line_total REAL NOT NULL CHECK(line_total >= 0),
                    notes TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_sales_quotations_customer
                ON sales_quotations(customer_id, quotation_date, id);
                """
            )

    def list_customers(self) -> list[dict]:
        return [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT id, name, COALESCE(phone, '') AS phone,
                       COALESCE(address, '') AS address
                FROM partners
                WHERE partner_type = 'customer' AND is_active = 1
                ORDER BY name
                """
            )
        ]

    def list_products(self) -> list[dict]:
        return [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT id, code, name, unit
                FROM products
                WHERE is_active = 1
                ORDER BY name
                """
            )
        ]

    def create_quotation(
        self,
        *,
        customer_id: int,
        lines: list[dict],
        notes: str = "",
        valid_until: str = "",
    ) -> int:
        if customer_id <= 0:
            raise ValueError("اختر العميل")
        if not lines:
            raise ValueError("أضف بندًا واحدًا على الأقل")

        normalized: list[dict] = []
        total = 0.0
        for line in lines:
            item_name = str(line.get("item_name", "")).strip()
            unit = str(line.get("unit", "")).strip() or "وحدة"
            quantity = float(line.get("quantity", 0))
            unit_price = float(line.get("unit_price", 0))
            if not item_name:
                raise ValueError("اسم الصنف مطلوب")
            if quantity <= 0:
                raise ValueError("الكمية يجب أن تكون أكبر من صفر")
            if unit_price < 0:
                raise ValueError("السعر لا يمكن أن يكون سالبًا")
            line_total = round(quantity * unit_price, 6)
            total += line_total
            normalized.append(
                {
                    "product_id": line.get("product_id"),
                    "item_name": item_name,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "notes": str(line.get("notes", "")).strip(),
                }
            )

        with self.database.session(immediate=True) as connection:
            next_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM sales_quotations"
                ).fetchone()[0]
            )
            number = f"QT{next_id:05d}"
            cursor = connection.execute(
                """
                INSERT INTO sales_quotations(
                    quotation_number, customer_id, valid_until, total, notes
                ) VALUES (?, ?, NULLIF(?, ''), ?, ?)
                """,
                (number, customer_id, valid_until.strip(), total, notes.strip()),
            )
            quotation_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO sales_quotation_lines(
                    quotation_id, product_id, item_name, quantity, unit,
                    unit_price, line_total, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        quotation_id,
                        line["product_id"],
                        line["item_name"],
                        line["quantity"],
                        line["unit"],
                        line["unit_price"],
                        line["line_total"],
                        line["notes"],
                    )
                    for line in normalized
                ],
            )
        return quotation_id

    def list_quotations(self) -> list[dict]:
        return [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT q.id, q.quotation_number, q.quotation_date, q.valid_until,
                       q.status, q.total, q.notes, p.name AS customer_name,
                       COALESCE(p.phone, '') AS customer_phone,
                       COUNT(ql.id) AS line_count
                FROM sales_quotations q
                JOIN partners p ON p.id = q.customer_id
                LEFT JOIN sales_quotation_lines ql ON ql.quotation_id = q.id
                GROUP BY q.id, q.quotation_number, q.quotation_date, q.valid_until,
                         q.status, q.total, q.notes, p.name, p.phone
                ORDER BY q.id DESC
                """
            )
        ]

    def get_print_data(self, quotation_id: int) -> dict:
        header = self.database.fetch_one(
            """
            SELECT q.id, q.quotation_number, q.quotation_date, q.valid_until,
                   q.status, q.total, q.notes, p.name AS customer_name,
                   COALESCE(p.phone, '') AS customer_phone,
                   COALESCE(p.address, '') AS customer_address
            FROM sales_quotations q
            JOIN partners p ON p.id = q.customer_id
            WHERE q.id = ?
            """,
            (quotation_id,),
        )
        if header is None:
            raise ValueError("عرض السعر غير موجود")
        lines = [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT item_name AS name, quantity, unit, unit_price,
                       line_total, COALESCE(notes, '') AS notes
                FROM sales_quotation_lines
                WHERE quotation_id = ?
                ORDER BY id
                """,
                (quotation_id,),
            )
        ]
        result = dict(header)
        result.update(
            {
                "document_title": "عرض سعر",
                "document_number_label": "رقم العرض",
                "invoice_number": result["quotation_number"],
                "invoice_date": result["quotation_date"],
                "order_number": "—",
                "payment_methods": "—",
                "paid": 0.0,
                "remaining": float(result["total"]),
                "lines": lines,
            }
        )
        return result


__all__ = ["QuotationRepository"]
