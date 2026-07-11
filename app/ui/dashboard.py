from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.repositories.inventory_repository import InventoryRepository
from app.repositories.product_repository import ProductRepository


class DashboardPage(QWidget):
    def __init__(
        self, product_repository: ProductRepository, inventory_repository: InventoryRepository
    ) -> None:
        super().__init__()
        self.product_repository = product_repository
        self.inventory_repository = inventory_repository
        self.setLayoutDirection(Qt.RightToLeft)
        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("الرئيسية"))
        layout.addWidget(QLabel("مؤشرات المخزون"))
        layout.addLayout(self.grid)
        layout.addStretch()
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        self._clear_cards()
        summary = self.product_repository.count_by_type()
        cards = [
            ("إجمالي الأصناف", str(summary["total"])),
            ("أصناف لها رصيد", str(self.inventory_repository.count_products_with_stock())),
            (
                "رصيد الخامات",
                str(round(self.inventory_repository.total_quantity_by_type("raw_material"), 2)),
            ),
            (
                "رصيد المنتجات",
                str(round(self.inventory_repository.total_quantity_by_type("finished_good"), 2)),
            ),
            (
                "رصيد الهالك",
                str(round(self.inventory_repository.total_quantity_by_type("waste"), 2)),
            ),
            ("قيمة المخزون", f"{self.inventory_repository.total_inventory_value():,.2f}"),
            ("نقص المخزون", str(self.inventory_repository.count_low_stock())),
        ]
        for index, card in enumerate(cards):
            self.grid.addWidget(self._card(card[0], card[1]), index // 2, index % 2)

    def _clear_cards(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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
