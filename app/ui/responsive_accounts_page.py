from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHeaderView

from app.ui.clickable_summary_accounts_page import ClickableSummaryAccountsPage


class ResponsiveAccountsPage(ClickableSummaryAccountsPage):
    """Accounts page with usable bank/treasury fields on large and small screens."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._expand_financial_account_editor()

    def _expand_financial_account_editor(self) -> None:
        for name, width in (
            ("account_code_input", 320),
            ("account_name_input", 460),
            ("opening_balance_input", 260),
            ("account_notes_input", 460),
        ):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setMinimumWidth(width)
                widget.setMinimumHeight(40)

        account_type = getattr(self, "account_type_input", None)
        if account_type is not None:
            account_type.setMinimumWidth(320)
            account_type.setMinimumHeight(40)

        accounts_table = getattr(self, "accounts_table", None)
        if accounts_table is not None:
            accounts_table.setMinimumHeight(260)
            accounts_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            accounts_table.horizontalHeader().setStretchLastSection(True)

        movements_table = getattr(self, "movements_table", None)
        if movements_table is not None:
            movements_table.setMinimumHeight(300)
            movements_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            movements_table.horizontalHeader().setStretchLastSection(True)

        for layout in self.findChildren(QFormLayout):
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)


__all__ = ["ResponsiveAccountsPage"]
