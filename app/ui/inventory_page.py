from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.inventory_repository import InventoryRepository


class InventoryPage(QWidget):
    def __init__(self, repository: InventoryRepository) -> None:
        super().__init__()
        self.repository = repository
        self.rows: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المخازن")
        title.setObjectName("titleLabel")
        subtitle = QLabel("الرصيد ناتج من حركات المخزون فقط. استخدم التسوية للرصيد الافتتاحي أو الجرد.")
        subtitle.setObjectName("subtitleLabel")

        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText("كمية التسوية: موجب للإضافة، سالب للخصم")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("ملاحظات")
        adjust_button = QPushButton("تسجيل تسوية للصنف المحدد")
        adjust_button.clicked.connect(self.post_adjustment)

        adjustment_layout = QHBoxLayout()
        adjustment_layout.addWidget(adjust_button)
        adjustment_layout.addWidget(self.quantity_input)
        adjustment_layout.addWidget(self.notes_input)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الكود", "الصنف", "النوع", "الوحدة", "الرصيد الحالي"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(adjustment_layout)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def post_adjustment(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            QMessageBox.warning(self, "تنبيه", "اختار صنف من الجدول أولًا")
            return
        try:
            quantity = float(self.quantity_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "اكتب كمية صحيحة")
            return
        self.repository.post_adjustment(
            int(self.rows[row]["id"]),
            quantity,
            self.notes_input.text().strip(),
        )
        self.quantity_input.clear()
        self.notes_input.clear()
        self.reload()

    def reload(self) -> None:
        self.rows = self.repository.list_stock_on_hand()
        self.table.setRowCount(len(self.rows))
        for row_index, item in enumerate(self.rows):
            values = [
                item["code"],
                item["name"],
                item["product_type"],
                item["unit"],
                str(item["quantity"]),
            ]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))
