from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.inventory_repository import InventoryRepository


class LotBalancesPage(QWidget):
    def __init__(self, repository: InventoryRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("أرصدة الدفعات")
        title.setObjectName("titleLabel")
        subtitle = QLabel("الرصيد والقيمة المتبقية لكل دفعة وفق الصرف بنظام FIFO.")
        subtitle.setObjectName("subtitleLabel")

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            [
                "الكود",
                "الصنف",
                "المخزن",
                "رقم الدفعة",
                "تاريخ الاستلام",
                "المستلم",
                "المصروف",
                "المتبقي",
                "متوسط التكلفة",
                "القيمة",
            ]
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        rows = self.repository.list_lot_balances()
        self.table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [
                item["code"],
                item["name"],
                item["warehouse_name"],
                item["lot_number"],
                item["received_at"],
                f"{float(item['quantity_received']):g} {item['unit']}",
                f"{float(item['quantity_issued']):g} {item['unit']}",
                f"{float(item['quantity_remaining']):g} {item['unit']}",
                f"{float(item['average_cost']):.4f}",
                f"{float(item['inventory_value']):.2f}",
            ]
            for column_index, value in enumerate(values):
                self.table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(str(value)),
                )
