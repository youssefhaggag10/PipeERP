from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.repositories.product_repository import ProductRepository


class DashboardPage(QWidget):
    def __init__(self, product_repository: ProductRepository) -> None:
        super().__init__()
        self.product_repository = product_repository
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الرئيسية")
        title.setObjectName("titleLabel")
        subtitle = QLabel("متابعة بيانات المصنع")
        subtitle.setObjectName("subtitleLabel")

        self.grid = QGridLayout()
        self.grid.setSpacing(14)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(self.grid)
        layout.addStretch()
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        summary = self.product_repository.count_by_type()
        cards = [
            ("إجمالي الأصناف", str(summary["total"])),
            ("الخامات", str(summary["raw_material"])),
            ("المنتجات", str(summary["finished_good"])),
            ("الهالك", str(summary["waste"])),
        ]
        for index, card in enumerate(cards):
            self.grid.addWidget(self._card(card[0], card[1]), index // 2, index % 2)

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
