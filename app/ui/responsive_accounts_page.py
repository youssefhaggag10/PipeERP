from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
)

from app.ui.clickable_summary_accounts_page import ClickableSummaryAccountsPage


class ResponsiveAccountsPage(ClickableSummaryAccountsPage):
    """Accounts page with a responsive, scrollable treasury and bank editor."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._configure_financial_controls()
        self._make_treasury_tab_scrollable()

    def _configure_financial_controls(self) -> None:
        for name, minimum_width in (
            ("account_code_input", 180),
            ("account_name_input", 240),
            ("opening_balance_input", 180),
            ("account_notes_input", 240),
        ):
            widget = getattr(self, name, None)
            if widget is None:
                continue
            widget.setMinimumWidth(minimum_width)
            widget.setMaximumWidth(16777215)
            widget.setMinimumHeight(38)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        account_type = getattr(self, "account_type_input", None)
        if account_type is not None:
            account_type.setMinimumWidth(180)
            account_type.setMaximumWidth(16777215)
            account_type.setMinimumHeight(38)
            account_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        for table_name, minimum_height in (
            ("accounts_table", 230),
            ("movements_table", 300),
            ("transactions_table", 280),
        ):
            table = getattr(self, table_name, None)
            if table is None:
                continue
            table.setMinimumHeight(minimum_height)
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)

        for layout in self.findChildren(QFormLayout):
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            layout.setFormAlignment(Qt.AlignTop | Qt.AlignRight)
            layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.setHorizontalSpacing(12)
            layout.setVerticalSpacing(10)

    def _make_treasury_tab_scrollable(self) -> None:
        tabs = self.findChild(QTabWidget)
        if tabs is None:
            return
        treasury_index = -1
        for index in range(tabs.count()):
            if tabs.tabText(index).strip() == "الخزينة والبنوك":
                treasury_index = index
                break
        if treasury_index < 0:
            return

        treasury_widget = tabs.widget(treasury_index)
        if treasury_widget is None or isinstance(treasury_widget, QScrollArea):
            return
        current_index = tabs.currentIndex()
        title = tabs.tabText(treasury_index)
        icon = tabs.tabIcon(treasury_index)
        tooltip = tabs.tabToolTip(treasury_index)

        treasury_widget.setMinimumSize(0, 0)
        treasury_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        scroll = QScrollArea()
        scroll.setObjectName("treasuryAccountsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(treasury_widget)

        tabs.removeTab(treasury_index)
        tabs.insertTab(treasury_index, scroll, icon, title)
        tabs.setTabToolTip(treasury_index, tooltip)
        tabs.setCurrentIndex(current_index)


__all__ = ["ResponsiveAccountsPage"]
