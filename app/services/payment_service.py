from sqlite3 import Connection


def post_order_payment(
    connection: Connection,
    *,
    transaction_type: str,
    partner_id: int,
    amount: float,
    reference_type: str | None,
    reference_id: int | None,
    notes: str = "",
    payment_method: str = "نقدي",
) -> int:
    if amount <= 0:
        raise ValueError("قيمة الدفع يجب أن تكون أكبر من صفر")
    next_id = int(
        connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM payment_transactions"
        ).fetchone()["next_id"]
    )
    prefix = "CR" if transaction_type == "customer_receipt" else "SP"
    transaction_number = f"{prefix}{next_id:06d}"
    cursor = connection.execute(
        """
        INSERT INTO payment_transactions(
            transaction_number, transaction_type, partner_id, amount,
            payment_method, reference_type, reference_id, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_number,
            transaction_type,
            partner_id,
            amount,
            payment_method.strip() or "نقدي",
            reference_type,
            reference_id,
            notes.strip(),
        ),
    )
    return int(cursor.lastrowid)
