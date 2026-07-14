from datetime import date

from app.database.connection import Database
from app.repositories.accounting_repository import AccountingRepository
from app.services.payment_service import post_order_payment


EPSILON = 0.000001


class ReversibleAccountingRepository(AccountingRepository):
    """Accounting repository with auditable payment reversals and advances."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self._ensure_reversal_schema()
       