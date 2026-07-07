from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.repositories.inventory_repository import InventoryRepository
from app.repositories.product_repository import ProductRepository


class DashboardPage(QWidget):
    def __init__(self, product_repository: ProductRepository, inventory_repository: InventoryRepository) -> None:
        super().__init__()
        self.product_repository = product_repository
        self.inventory_repository = inventory_repository
        self.setLayoutDirection(Qt.RightToLeft)
        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("\u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629"))
        layout.addWidget(QLabel("\u0645\u0624\u0634\u0631\u0627\u062a \u0627\u0644\u0645\u062e\u0632\u0648\u0646"))
        layout.addLayout(self.grid)
        layout.addStretch()
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        summary = self.product_repository.count_by_type()
        cards = [
            ("\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0623\u0635\u0646\u0627\u0641", str(summary["total"])),
            ("\u0623\u0635\u0646\u0627\u0641 \u0644\u0647\u0627 \u0631\u0635\u064a\u062f", str(self.inventory_repository.count_products_with_stock())),
            ("\u0631\u0635\u064a\u062f \u0627\u0644\u062e\u0627\u0645\u0627\u062a", str(round(self.inventory_repository.total_quantity_by_type("raw_material"), 2))),
            ("\u0631\u0635\u064a\u062f \u0627\u0644\u0645\u0646\u062a\u062c\u0627\u062a", str(round(self.inventory_repository.total_quantity_by_type("finished_good"), 2))),
            ("\u0631\u0635\u064a\u062f \u0627\u0644\u0647\u0627\u0644\u0643", str(round(self.inventory_repository.total_quantity_by_type("waste"), 2))),
            ("\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0631\u0635\u064a\u062f", str(round(self.inventory_repository.total_quantity(), 2))),
            ("\u0646\u0642\u0635 \u0627\u0644\u0645\u062e\u0632\u0648\u0646", str(self.inventory_repository.count_low_stock())),
        ]
        for index, card in enumerate(cards):
            self.grid.addWidget(self._card(card[0], card[1]), index // 2, index % 2)

    def _card(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        label1 = QLabel(title)
        label2 = QLabel(value)
        label2.setStyleSheet("font-size: 26px; font-weight: 800; color: #38BDF8;")
        layout = QVBoxLayout()
        layout.addWidget(label1)
        layout.addWidget(label2)
        frame.setLayout(layout)
        return frame
