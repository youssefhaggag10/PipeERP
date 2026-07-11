from app.database.connection import Database
from app.models.user import User


class CRMCustomerSync:
    """Keep active customer master records visible inside CRM.

    Existing customers are represented as won/current CRM records. A matching
    unlinked lead is reused by phone when possible, otherwise a new CRM record
    is created. The customer master remains the source of truth for the core
    name, phone, and address fields.
    """

    def __init__(self, database: Database