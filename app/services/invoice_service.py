from sqlite3 import Connection

INVOICE_STATUS_LABELS = {
    "draft": "مسودة",
    "posted": "معتمدة",
    "cancelled": "ملغاة",
}

PAYMENT_STATUS_LABELS = {
    "unpaid": "غير مدفوعة",
    "partial": "مدفوعة جزئيًا",
    "paid": "مدفوعة بالكامل",
    "cancelled": "—",
}


def payment_status(total: float, paid: float, invoice_status: str) -> str:
    if invoice_status == "cancelled":
        return "cancelled"
    if paid <= 0.000001:
        return "unpaid"
    if total - paid <= 0.000001:
        return "paid"
    return "partial"


def create_invoice_for_order(
    connection: Connection,
    *,
    invoice_type: str,
    order_id: int,
    partner_id: int,
    total: float,
    status: str = "draft",
    notes: str = "",
) -> tuple[int, str]:
    normalized_notes = notes.strip()

    if invoice_type == "sales":
        existing = connection.execute(
            "SELECT id, invoice_number FROM sales_invoices WHERE sales_order_id = ?",
            (order_id,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"]), str(existing["invoice_number"])

        next_id = int(
            connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sales_invoices"
            ).fetchone()["next_id"]
        )
        invoice_number = f"SI{next_id:05d}"
        cursor = connection.execute(
            """
            INSERT INTO sales_invoices(
                invoice_number, sales_order_id, customer_id, status,
                total, notes, posted_at
            )
            VALUES (?, ?, ?, ?, ?, ?,
                    CASE WHEN ? = 'posted' THEN CURRENT_TIMESTAMP ELSE NULL END)
            """,
            (
                invoice_number,
                order_id,
                partner_id,
                status,
                total,
                normalized_notes,
                status,
            ),
        )
        return int(cursor.lastrowid), invoice_number

    if invoice_type == "purchase":
        existing = connection.execute(
            "SELECT id, invoice_number FROM purchase_invoices WHERE purchase_order_id = ?",
            (order_id,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"]), str(existing["invoice_number"])

        next_id = int(
            connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM purchase_invoices"
            ).fetchone()["next_id"]
        )
        invoice_number = f"PI{next_id:05d}"
        cursor = connection.execute(
            """
            INSERT INTO purchase_invoices(
                invoice_number, purchase_order_id, supplier_id, status,
                total, notes, posted_at
            )
            VALUES (?, ?, ?, ?, ?, ?,
                    CASE WHEN ? = 'posted' THEN CURRENT_TIMESTAMP ELSE NULL END)
            """,
            (
                invoice_number,
                order_id,
                partner_id,
                status,
                total,
                normalized_notes,
                status,
            ),
        )
        return int(cursor.lastrowid), invoice_number

    raise ValueError("نوع الفاتورة غير صحيح")
