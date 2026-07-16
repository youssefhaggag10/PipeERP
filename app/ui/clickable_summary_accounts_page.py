from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QGroupBox, QLabel, QMessageBox

from app.ui.accounts_summary_details_dialog import AccountsSummaryDetailsDialog
from app.ui.return_refund_accounts_page import ReturnRefundAccountsPage


class ClickableSummaryAccountsPage(ReturnRefundAccountsPage):
    """Account page whose summary cards open the exact rows behind each total."""

    CARD_KEYS = {
        "إجمالي فواتير المبيعات": "sales_total",
        "تحصيلات العملاء": "customer_receipts",
        "دفعات مقدمة من العملاء": "customer_advances",
        "مديونيات العملاء": "receivables",
        "إجمالي فواتير المشتريات": "purchases_total",
        "مدفوعات الموردين": "supplier_payments",
        "دفعات مقدمة للموردين": "supplier_advances",
        "مديونيات الموردين": "payables",
    }

    def __init__(self, *args, **kwargs) -> None:
        self._summary_click_targets: dict[QObject, str] = {}
        super().__init__(*args, **kwargs)
        self._configure_clickable_summary_cards()

    def _configure_clickable_summary_cards(self) -> None:
        for group in self.findChildren(QGroupBox):
            key = self.CARD_KEYS.get(group.title().strip())
            if key is None:
                continue
            group.setCursor(QCursor(Qt.PointingHandCursor))
            group.setToolTip("اضغط لعرض تفاصيل الرقم")
            group.installEventFilter(self)
            self._summary_click_targets[group] = key
            for label in group.findChildren(QLabel):
                label.setCursor(QCursor(Qt.PointingHandCursor))
                label.setToolTip("اضغط لعرض تفاصيل الرقم")
                label.installEventFilter(self)
                self._summary_click_targets[label] = key

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.MouseButtonRelease and watched in self._summary_click_targets:
            self._open_summary_details(self._summary_click_targets[watched])
            return True
        return super().eventFilter(watched, event)

    def _open_summary_details(self, key: str) -> None:
        if not hasattr(self.accounting_repository, "summary_card_details"):
            QMessageBox.warning(self, "تنبيه", "تفاصيل الملخص غير مفعلة")
            return
        try:
            summary = self.accounting_repository.dashboard_summary()
            details = self.accounting_repository.summary_card_details(key)
        except (ValueError, Exception) as error:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل تفاصيل الكارت: {error}")
            return

        dialog = AccountsSummaryDetailsDialog(
            title=str(details["title"]),
            total=float(summary.get(key, 0)),
            headers=list(details["headers"]),
            rows=list(details["rows"]),
            parent=self,
        )
        dialog.exec()


__all__ = ["ClickableSummaryAccountsPage"]
