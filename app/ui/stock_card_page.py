from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.inventory_repository import InventoryRepository


class StockCardPage(QWidget):
    def __init__(self, repository: InventoryRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setLayoutDirection(Qt.RightToLeft)
        title = QLabel("Stock Card")
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["Date", "Code", "Item", "Warehouse", "Lot", "In", "Out", "Cost", "Ref", "Partner"])
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        rows = self.repository.list_stock_card()
        self.table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [
                item["move_date"], item["code"], item["name"], item["warehouse_name"], item["lot_number"],
                item["quantity_in"], item["quantity_out"], item["unit_cost"], item["reference_type"], item["partner_name"]
            ]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
