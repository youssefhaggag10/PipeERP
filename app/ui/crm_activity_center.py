from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.utils.datetime_utils import format_egypt_datetime

ACTIVITY_LABELS = {
    "call": "مكالمة",
    "whatsapp": "واتساب",
    "message": "رسالة",
    "meeting": "اجتماع",
    "visit": "زيارة",
    "email": "بريد",
    "task": "مهمة",
}


class CRMActivityCenter(QToolButton):
    open_crm_requested = Signal()

    def __init__(self, repository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.setObjectName("activityCenterButton")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("أنشطة ومتابعات CRM")
        self.menu = QMenu(self)
        self.menu.setMinimumWidth(470)
        self.setMenu(self.menu)

        self.timer = QTimer(self)
        self.timer.setInterval(60_000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        try:
            activities = self.repository.list_activities("scheduled")
        except Exception:
            activities = []

        overdue = [row for row in activities if row.get("display_status") == "overdue"]
        today = [row for row in activities if row.get("display_status") == "today"]
        future = [
            row for row in activities if row.get("display_status") not in {"overdue", "today"}
        ]

        attention_count = len(overdue) + len(today)
        self.setText(f"🔔 الأنشطة {attention_count}" if attention_count else "🔔 الأنشطة")
        self.setProperty("hasAttention", bool(attention_count))
        self.style().unpolish(self)
        self.style().polish(self)

        self.menu.clear()
        self._add_header(len(overdue), len(today), len(future))

        if not activities:
            action = QWidgetAction(self.menu)
            label = QLabel("لا توجد أنشطة مجدولة")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(60)
            action.setDefaultWidget(label)
            self.menu.addAction(action)
            return

        for activity in activities[:25]:
            self._add_activity(activity)

        if len(activities) > 25:
            self.menu.addSeparator()
            more = self.menu.addAction(f"عرض باقي الأنشطة ({len(activities) - 25})")
            more.triggered.connect(self.open_crm_requested.emit)

        self.menu.addSeparator()
        all_action = self.menu.addAction("فتح جميع أنشطة CRM")
        all_action.triggered.connect(self.open_crm_requested.emit)

    def _add_header(self, overdue: int, today: int, future: int) -> None:
        action = QWidgetAction(self.menu)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("مركز أنشطة CRM")
        title.setStyleSheet("font-size: 16px; font-weight: 800;")
        counts = QLabel(f"متأخر: {overdue}   |   اليوم: {today}   |   قادم: {future}")
        counts.setObjectName("subtitleLabel")
        layout.addWidget(title)
        layout.addWidget(counts)
        action.setDefaultWidget(widget)
        self.menu.addAction(action)
        self.menu.addSeparator()

    def _add_activity(self, activity: dict) -> None:
        action = QWidgetAction(self.menu)
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        status = str(activity.get("display_status", "scheduled"))
        status_label = {
            "overdue": "متأخر",
            "today": "اليوم",
            "scheduled": "قادم",
        }.get(status, status)
        activity_type = ACTIVITY_LABELS.get(
            str(activity.get("activity_type", "")),
            str(activity.get("activity_type", "")),
        )

        top = QHBoxLayout()
        subject = QLabel(str(activity.get("subject", "متابعة")))
        subject.setStyleSheet("font-weight: 800;")
        badge = QLabel(status_label)
        if status == "overdue":
            badge.setStyleSheet(
                "background:#DC2626;color:white;padding:3px 7px;border-radius:6px;font-weight:700;"
            )
        elif status == "today":
            badge.setStyleSheet(
                "background:#D97706;color:white;padding:3px 7px;border-radius:6px;font-weight:700;"
            )
        else:
            badge.setStyleSheet(
                "background:#2563EB;color:white;padding:3px 7px;border-radius:6px;font-weight:700;"
            )
        top.addWidget(subject, 1)
        top.addWidget(badge)

        customer = QLabel(
            f"{activity_type} مع {activity.get('lead_name', '')} — {activity.get('phone', '')}"
        )
        customer.setObjectName("subtitleLabel")
        due = QLabel(
            f"الموعد: {format_egypt_datetime(activity.get('due_at'))}"
            f" — المسؤول: {activity.get('owner_name', '') or 'غير محدد'}"
        )
        due.setObjectName("subtitleLabel")

        open_button = QPushButton("فتح النشاط في CRM")
        open_button.setObjectName("secondaryButton")
        open_button.clicked.connect(self._open_crm)

        layout.addLayout(top)
        layout.addWidget(customer)
        layout.addWidget(due)
        layout.addWidget(open_button)
        action.setDefaultWidget(frame)
        self.menu.addAction(action)

    def _open_crm(self) -> None:
        self.menu.close()
        self.open_crm_requested.emit()


__all__ = ["CRMActivityCenter"]
