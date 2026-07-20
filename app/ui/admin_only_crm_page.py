from PySide6.QtWidgets import QMessageBox, QPushButton

from app.ui.crm_page import CRMPage


class AdminOnlyCRMPage(CRMPage):
    """Expose CRM activity scheduling only to administrators."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._apply_schedule_permission()

    def _apply_schedule_permission(self) -> None:
        allowed = bool(getattr(self.repo, "can_schedule_activities", False))
        for button in self.findChildren(QPushButton):
            if button.text().strip() == "جدولة نشاط":
                button.setEnabled(allowed)
                button.setToolTip(
                    "جدولة الأنشطة متاحة للأدمن فقط" if not allowed else "جدولة نشاط للعميل المحدد"
                )

    def schedule_activity(self) -> None:
        if not bool(getattr(self.repo, "can_schedule_activities", False)):
            QMessageBox.warning(self, "غير مسموح", "جدولة الأنشطة متاحة للأدمن فقط")
            return
        super().schedule_activity()


__all__ = ["AdminOnlyCRMPage"]
