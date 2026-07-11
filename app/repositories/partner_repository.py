from app.database.connection import Database


class PartnerRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_partners(self, partner_type: str) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT id, code, name, phone, address, opening_balance, is_active
            FROM partners
            WHERE partner_type = ? AND is_active = 1
            ORDER BY id DESC
            """,
            (partner_type,),
        )
        return [dict(row) for row in rows]

    def create_partner(
        self, partner_type: str, code: str, name: str, phone: str = "", address: str = ""
    ) -> int:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO partners(partner_type, code, name, phone, address)
                VALUES (?, ?, ?, ?, ?)
                """,
                (partner_type, code.strip() or None, name.strip(), phone.strip(), address.strip()),
            )
            return int(cursor.lastrowid)

    def delete_partner(self, partner_id: int) -> None:
        with self.database.session() as connection:
            connection.execute("UPDATE partners SET is_active = 0 WHERE id = ?", (partner_id,))

    def list_partner_moves(self, partner_id: int) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT m.move_date, p.code, p.name, m.quantity_in, m.quantity_out,
                   m.unit_cost, m.reference_type, m.reference_id, COALESCE(m.notes, '') AS notes
            FROM inventory_moves m
            JOIN products p ON p.id = m.product_id
            WHERE m.partner_id = ?
            ORDER BY m.id DESC
            """,
            (partner_id,),
        )
        return [dict(row) for row in rows]
