from pathlib import Path

from PySide6.QtWidgets import QApplication, QScrollArea, QTabWidget

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.detailed_return_refund_repository import DetailedReturnRefundRepository
from app.repositories.partner_repository import PartnerRepository
from app.repositories.return_refund_invoice_repository import ReturnRefundInvoiceRepository
from app.ui.responsive_accounts_page import ResponsiveAccountsPage


def test_treasury_and_banks_tab_is_scrollable_and_responsive(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "responsive-accounts.sqlite3")
    initialize_database(database)

    page = ResponsiveAccountsPage(
        DetailedReturnRefundRepository(database),
        PartnerRepository(database),
        ReturnRefundInvoiceRepository(database),
    )
    page.show()
    app.processEvents()

    tabs = page.findChild(QTabWidget)
    assert tabs is not None
    treasury_index = next(
        index
        for index in range(tabs.count())
        if tabs.tabText(index).strip() == "الخزينة والبنوك"
    )
    scroll = tabs.widget(treasury_index)
    assert isinstance(scroll, QScrollArea)
    assert scroll.widgetResizable()
    assert scroll.objectName() == "treasuryAccountsScrollArea"

    assert page.account_name_input.minimumWidth() <= 240
    assert page.accounts_table.minimumHeight() >= 230
    assert page.movements_table.minimumHeight() >= 300

    page.close()
    app.processEvents()
