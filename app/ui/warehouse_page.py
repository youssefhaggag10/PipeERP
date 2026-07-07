from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.warehouse_repository import WarehouseRepository


class WarehousePage(QWidget):
    def __init__(self, repository: WarehouseRepository) -> None:
        super().__init__()
        self.repository = repository
        self.rows = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المخازن")
        title.setObjectName("titleLabel")
        self.code_input = QLineEdit()
        self.name_input = QLineEdit()

        form = QFormLayout()
        form.addRow("الكود", self.code_input)
        form.addRow("الاسم", self.name_input)

        save_button = QPushButton("حفظ")
        save_button.clicked.connect(self.save_record)
        delete_button = QPushButton("حذف المحدد")
        delete_button.clicked.connect(self.delete_selected)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(delete_button)
        actions.addStretch()

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["الكود", "الاسم"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def save_record(self) -> None:
        if not self.code_input.text().strip() or not self.name_input.text().strip():
            QMessageBox.warning(self, "تنبيه", "الكود والاسم مطلوبين")
            return
        self.repository.create_warehouse(self.code_input.text(), self.name_input.text())
        self.code_input.clear()
        self.name_input.clear()
        self.reload()

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            QMessageBox.warning(self, "تنبيه", "اختار صف من الجدول")
            return
        self.repository.delete_warehouse(int(self.rows[row]["id"]))
        self.reload()

    def reload(self) -> None:
        self.rows = self.repository.list_warehouses()
        self.table.setRowCount(len(self.rows))
        for row_index, item in enumerate(self.rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(str(item["code"])))
            self.table.setItem(row_index, 1, QTableWidgetItem(str(item["name"])))
