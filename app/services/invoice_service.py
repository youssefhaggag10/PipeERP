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
    if invoice_type == "sales":
        table = "sales_invoices"
        order_column = "sales_order_id"
        partner_column = "customer_id"
        prefix = "SI"
    elif invoice_type == "purchase":
        table = "purchase_invoices"
        order_column = "purchase_order_id"
        partner_column = "supplier_id"
        prefix = "PI"
    else:
        raise ValueError("نوع الفاتورة غير صحيح")

    existing = connection.execute(
        f"SELECT id, invoice_number FROM {table} WHERE {order_column} = ?",
        (order_id,),
    ).fetchone()
    if existing is not None:
        return int(existing["id"]), str(existing["invoice_number"])

    next_id = int(
        connection.execute(f"SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM {table}")
        .fetchone()["next_id"]
    )
    invoice_number = f"{prefix}{next_id:05d}"
    posted_at_sql = "CURRENT_TIMESTAMP" if status == "posted" else "NULL"
    cursor = connection.execute(
        f"""
        INSERT INTO {table}(
            invoice_number, {order_column}, {partner_column}, status,
            total, notes, posted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, {posted_at_sql})
        """,
        (invoice_number, order_id, partner_id, status, total, notes.strip()),
    )
    return int(cursor.lastrowid), invoice_number
