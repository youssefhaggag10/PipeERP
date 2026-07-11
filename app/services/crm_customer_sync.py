from app.database.connection import Database
from app.models.user import User


class CRMCustomerSync:
    """Synchronize active customer master records into CRM.

    Existing customers are represented in CRM as current/won customers. A lead
    with the same phone is reused when it is not already linked to another
    customer, otherwise a new CRM record is created. Repeated synchronization
    is safe and does not create duplicate records.
    """

    def __init__(self, database: Database, current_user: User) -> None:
        self.database = database
        self.current_user = current_user

    def sync(self) -> int:
        """Return the number of customers newly added or linked to CRM."""
        synced = 0
        with self.database.session(immediate=True) as connection:
            # CRM may not exist in older databases until CRMRepository initializes it.
            crm_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='crm_leads'"
            ).fetchone()
            if crm_table is None:
                return 0

            customers = connection.execute(
                """
                SELECT id, code, name, COALESCE(phone, '') AS phone,
                       COALESCE(address, '') AS address, created_at
                FROM partners
                WHERE partner_type = 'customer' AND is_active = 1
                ORDER BY id
                """
            ).fetchall()

            for customer in customers:
                partner_id = int(customer["id"])
                phone = str(customer["phone"] or "").strip()

                linked = connection.execute(
                    "SELECT id FROM crm_leads WHERE customer_partner_id = ? LIMIT 1",
                    (partner_id,),
                ).fetchone()
                if linked is not None:
                    connection.execute(
                        """
                        UPDATE crm_leads
                        SET name = ?, phone = ?, address = ?,
                            customer_type = 'customer', stage_code = 'won',
                            is_active = 1, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            customer["name"],
                            phone,
                            customer["address"],
                            int(linked["id"]),
                        ),
                    )
                    continue

                matching_lead = None
                if phone:
                    matching_lead = connection.execute(
                        """
                        SELECT id FROM crm_leads
                        WHERE phone = ? AND is_active = 1
                          AND customer_partner_id IS NULL
                        ORDER BY id DESC LIMIT 1
                        """,
                        (phone,),
                    ).fetchone()

                if matching_lead is not None:
                    lead_id = int(matching_lead["id"])
                    connection.execute(
                        """
                        UPDATE crm_leads
                        SET name = ?, address = ?, customer_partner_id = ?,
                            customer_type = 'customer', stage_code = 'won',
                            assigned_user_id = COALESCE(assigned_user_id, ?),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            customer["name"],
                            customer["address"],
                            partner_id,
                            self.current_user.id,
                            lead_id,
                        ),
                    )
                    subject = "ربط العميل الحالي بسجل CRM"
                else:
                    next_id = int(
                        connection.execute(
                            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM crm_leads"
                        ).fetchone()["next_id"]
                    )
                    lead_number = f"LD{next_id:05d}"
                    cursor = connection.execute(
                        """
                        INSERT INTO crm_leads(
                            lead_number, name, phone, address, source_code,
                            customer_type, temperature, stage_code,
                            assigned_user_id, tags, general_notes,
                            customer_partner_id, created_by, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, 'other', 'customer', 'warm', 'won',
                                ?, 'عميل سابق', ?, ?, ?,
                                COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
                        """,
                        (
                            lead_number,
                            customer["name"],
                            phone,
                            customer["address"],
                            self.current_user.id,
                            f"تمت المزامنة من شاشة العملاء — الكود: {customer['code'] or '-'}",
                            partner_id,
                            self.current_user.id,
                            customer["created_at"],
                        ),
                    )
                    lead_id = int(cursor.lastrowid)
                    subject = "استيراد عميل حالي إلى CRM"

                connection.execute(
                    """
                    INSERT INTO crm_activities(
                        lead_id, activity_type, subject, notes,
                        assigned_user_id, status, created_by, completed_at
                    )
                    VALUES (?, 'conversion', ?, ?, ?, 'done', ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        lead_id,
                        subject,
                        f"تم الربط بالعميل رقم {partner_id}",
                        self.current_user.id,
                        self.current_user.id,
                    ),
                )
                synced += 1

        return synced
