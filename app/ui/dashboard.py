from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الرئيسية")
        title.setObjectName("titleLabel")
        subtitle = QLabel("متابعة سريعة للمصنع والمخزون")
        subtitle.setObjectName("subtitleLabel")

        grid = QGridLayout()
        grid.setSpacing(14)
        cards = [
            ("رصيد الخامات", "0 كجم"),
            ("إنتاج اليوم", "0 كجم"),
            ("الهالك المتاح", "0 كجم"),
            ("تنبيهات المخزون", "0"),
        ]
        for index, card in enumerate(cards):
            grid.addWidget(self._card(card[0], card[1]), index // 2, index % 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(grid)
        layout.addStretch()
        self.setLayout(layout)

    def _card(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setMinimumHeight(120)
        title_label = QLabel(title)
        title_label.setObjectName("subtitleLabel")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 26px; font-weight: 800; color: #38BDF8;")

        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        frame.setLayout(layout)
        return frame
