from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.partner_repository import PartnerRepository


class PartnersPage(QWidget):
    def __init__(self, title: str, partner_type: str, repository: PartnerRepository) -> None:
        super().__init__()
        self.title = title
        self.partner_type = partner_type
        self.repository = repository
        self.rows: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")

        self.code_input = QLineEdit()
        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.address_input = QLineEdit()

        form = QFormLayout()
        form.addRow("الكود", self.code_input)
        form.addRow("الاسم", self.name_input)
        form.addRow("الهاتف", self.phone_input)
        form.addRow("العنوان", self.address_input)

        save_button = QPushButton("حفظ")
        save_button.clicked.connect(self.save_partner)
        delete_button = QPushButton("حذف المحدد")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_selected)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(delete_button)
        actions.addStretch()

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["الكود", "الاسم", "الهاتف", "العنوان"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title_label)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def save_partner(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "تنبيه", "الاسم مطلوب")
            return
        self.repository.create_partner(
            self.partner_type,
            self.code_input.text(),
            name,
            self.phone_input.text(),
            self.address_input.text(),
        )
        self.code_input.clear()
        self.name_input.clear()
        self.phone_input.clear()
        self.address_input.clear()
        self.reload()

    def delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.rows):
            QMessageBox.warning(self, "تنبيه", "اختار صف من الجدول")
            return
        self.repository.delete_partner(int(self.rows[row]["id"]))
        self.reload()

    def reload(self) -> None:
        self.rows = self.repository.list_partners(self.partner_type)
        self.table.setRowCount(len(self.rows))
        for row_index, item in enumerate(self.rows):
            values = [item["code"] or "", item["name"], item["phone"] or "", item["address"] or ""]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
