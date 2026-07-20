from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.treasury_order_pages import TreasurySalesAccountingPageWithPrint


CARD_STATUS = {
    "draft": "مسودة",
    "posted": "معتمدة",
    "cancelled": "ملغاة",
}


class WeightCardsDialog(QDialog):
    def __init__(self, repository, sales_order_id: int, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.sales_order_id = int(sales_order_id)
        self.order_lines: list[dict] = []
        self.cards: list[dict] = []
        self.quantity_inputs: dict[int, QLineEdit] = {}
        self.setWindowTitle("كروت وزن أمر البيع")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1200, 780)

        explanation = QLabel(
            "اختر عدد المواسير من كل مقاس الموجودة على الكارتة، ثم أدخل الوزن "
            "الصافي الفعلي وسعر الكيلو. النظام يوزع وزن الكارتة على المقاسات "
            "بنسبة العدد × الوزن القياسي، بينما إجمالي الفاتورة يظل الوزن الفعلي × سعر الكيلو."
        )
        explanation.setWordWrap(True)

        self.lines_table = QTableWidget(0, 8)
        self.lines_table.setHorizontalHeaderLabels(
            [
                "الكود",
                "الصنف",
                "المطلوب",
                "سبق تحميله",
                "المتبقي",
                "الوزن القياسي",
                "عدد هذه الكارتة",
                "الوزن النظري",
            ]
        )
        self.lines_table.setSelectionMode(QTableWidget.NoSelection)
        self.lines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.card_number_input = QLineEdit()
        self.card_number_input.setPlaceholderText("اختياري — ينشئ النظام رقمًا تلقائيًا")
        self.vehicle_input = QLineEdit()
        self.vehicle_input.setPlaceholderText("رقم السيارة أو المقطورة")
        self.gross_input = QLineEdit()
        self.gross_input.setPlaceholderText("اختياري")
        self.tare_input = QLineEdit()
        self.tare_input.setPlaceholderText("اختياري")
        self.net_input = QLineEdit()
        self.net_input.setPlaceholderText("الوزن الصافي الفعلي بالكيلو")
        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("سعر الكيلو")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("ملاحظات كارتة الميزان")
        self.total_label = QLabel("قيمة الكارتة: 0.00")
        self.total_label.setStyleSheet("font-size:18px;font-weight:900;")
        self.net_input.textChanged.connect(self._refresh_total)
        self.price_input.textChanged.connect(self._refresh_total)

        form = QGridLayout()
        form.addWidget(QLabel("رقم الكارتة"), 0, 0)
        form.addWidget(self.card_number_input, 1, 0)
        form.addWidget(QLabel("السيارة"), 0, 1)
        form.addWidget(self.vehicle_input, 1, 1)
        form.addWidget(QLabel("الوزن القائم"), 0, 2)
        form.addWidget(self.gross_input, 1, 2)
        form.addWidget(QLabel("وزن الفارغ"), 0, 3)
        form.addWidget(self.tare_input, 1, 3)
        form.addWidget(QLabel("الوزن الصافي الفعلي"), 2, 0)
        form.addWidget(self.net_input, 3, 0)
        form.addWidget(QLabel("سعر الكيلو"), 2, 1)
        form.addWidget(self.price_input, 3, 1)
        form.addWidget(QLabel("ملاحظات"), 2, 2)
        form.addWidget(self.notes_input, 3, 2)
        form.addWidget(self.total_label, 3, 3)

        save_button = QPushButton("حفظ كارتة الوزن")
        save_button.clicked.connect(self.save_card)
        clear_button = QPushButton("تفريغ بيانات الكارتة")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self.clear_card_form)
        cancel_card_button = QPushButton("إلغاء الكارتة المحددة")
        cancel_card_button.setObjectName("dangerButton")
        cancel_card_button.clicked.connect(self.cancel_selected_card)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(clear_button)
        actions.addWidget(cancel_card_button)
        actions.addWidget(refresh_button)
        actions.addStretch()

        self.cards_table = QTableWidget(0, 10)
        self.cards_table.setHorizontalHeaderLabels(
            [
                "رقم الكارتة",
                "التاريخ",
                "السيارة",
                "عدد المقاسات",
                "عدد المواسير",
                "الوزن الصافي",
                "سعر الكيلو",
                "القيمة",
                "الحالة",
                "ملاحظات",
            ]
        )
        self.cards_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cards_table.setSelectionMode(QTableWidget.SingleSelection)
        self.cards_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cards_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.cards_table.horizontalHeader().setStretchLastSection(True)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.button(QDialogButtonBox.Close).setText("إغلاق")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addWidget(QLabel("محتويات الكارتة الجديدة"))
        layout.addWidget(self.lines_table, 3)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(QLabel("كروت الوزن المسجلة على الأمر"))
        layout.addWidget(self.cards_table, 2)
        layout.addWidget(close_buttons)
        self.reload()

    def reload(self) -> None:
        self._reload_order_lines()
        self._reload_cards()

    def _reload_order_lines(self) -> None:
        self.order_lines = self.repository.get_order_weight_lines(self.sales_order_id)
        self.quantity_inputs.clear()
        self.lines_table.setRowCount(len(self.order_lines))
        for row_index, line in enumerate(self.order_lines):
            standard = float(line["standard_weight_kg"] or 0)
            values = [
                line["code"],
                line["name"],
                f"{float(line['ordered_quantity']):g}",
                f"{float(line['allocated_quantity']):g}",
                f"{float(line['remaining_quantity']):g}",
                f"{standard:g} كجم",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.lines_table.setItem(row_index, column, item)
            quantity = QLineEdit("0")
            quantity.setPlaceholderText("عدد المواسير")
            quantity.textChanged.connect(
                lambda _text, row=row_index: self._refresh_theoretical_weight(row)
            )
            self.lines_table.setCellWidget(row_index, 6, quantity)
            theoretical = QTableWidgetItem("0.000 كجم")
            theoretical.setFlags(theoretical.flags() & ~Qt.ItemIsEditable)
            self.lines_table.setItem(row_index, 7, theoretical)
            self.quantity_inputs[int(line["sales_order_line_id"])] = quantity

    def _reload_cards(self) -> None:
        self.cards = self.repository.list_weight_cards(self.sales_order_id)
        self.cards_table.setRowCount(len(self.cards))
        for row_index, card in enumerate(self.cards):
            values = [
                card["card_number"],
                card["card_date"],
                card.get("vehicle_number", "") or "",
                card["line_count"],
                f"{float(card['total_pieces']):g}",
                f"{float(card['net_weight_kg']):,.3f}",
                f"{float(card['price_per_kg']):,.2f}",
                f"{float(card['total_amount']):,.2f}",
                CARD_STATUS.get(str(card["status"]), card["status"]),
                card.get("notes", "") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(card["id"]))
                self.cards_table.setItem(row_index, column, item)

    def _refresh_theoretical_weight(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self.order_lines):
            return
        line = self.order_lines[row_index]
        field = self.quantity_inputs.get(int(line["sales_order_line_id"]))
        try:
            quantity = float(field.text().strip() or 0) if field else 0
        except ValueError:
            quantity = 0
        theoretical = quantity * float(line["standard_weight_kg"] or 0)
        item = self.lines_table.item(row_index, 7)
        if item is not None:
            item.setText(f"{theoretical:,.3f} كجم")

    def _refresh_total(self) -> None:
        try:
            net = float(self.net_input.text().strip() or 0)
            price = float(self.price_input.text().strip() or 0)
            total = net * price
        except ValueError:
            total = 0
        self.total_label.setText(f"قيمة الكارتة: {total:,.2f}")

    def save_card(self) -> None:
        lines = []
        try:
            for line in self.order_lines:
                field = self.quantity_inputs[int(line["sales_order_line_id"])]
                quantity = float(field.text().strip() or 0)
                if quantity > 0:
                    lines.append(
                        {
                            "sales_order_line_id": int(line["sales_order_line_id"]),
                            "quantity_pieces": quantity,
                        }
                    )
            net_weight = float(self.net_input.text().strip())
            price = float(self.price_input.text().strip())
            gross = (
                float(self.gross_input.text().strip())
                if self.gross_input.text().strip()
                else None
            )
            tare = (
                float(self.tare_input.text().strip())
                if self.tare_input.text().strip()
                else None
            )
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الأعداد والأوزان والسعر يجب أن تكون أرقامًا")
            return
        try:
            card_id = self.repository.create_weight_card(
                self.sales_order_id,
                lines=lines,
                net_weight_kg=net_weight,
                price_per_kg=price,
                card_number=self.card_number_input.text(),
                vehicle_number=self.vehicle_input.text(),
                gross_weight_kg=gross,
                tare_weight_kg=tare,
                notes=self.notes_input.text(),
            )
        except (KeyError, ValueError) as error:
            QMessageBox.warning(self, "تعذر حفظ الكارتة", str(error))
            return
        self.clear_card_form()
        self.reload()
        QMessageBox.information(
            self,
            "تم حفظ كارتة الوزن",
            f"تم تسجيل الكارتة رقم {card_id} وتحديث قيمة أمر البيع والفاتورة المسودة.",
        )

    def clear_card_form(self) -> None:
        self.card_number_input.clear()
        self.vehicle_input.clear()
        self.gross_input.clear()
        self.tare_input.clear()
        self.net_input.clear()
        self.price_input.clear()
        self.notes_input.clear()
        for field in self.quantity_inputs.values():
            field.setText("0")
        self._refresh_total()

    def cancel_selected_card(self) -> None:
        row = self.cards_table.currentRow()
        if row < 0 or row >= len(self.cards):
            QMessageBox.warning(self, "تنبيه", "اختر كارتة من الجدول")
            return
        card = self.cards[row]
        answer = QMessageBox.question(
            self,
            "إلغاء كارتة الوزن",
            f"هل تريد إلغاء الكارتة {card['card_number']} وإعادة حساب قيمة الأمر؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repository.cancel_weight_card(int(card["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الإلغاء", str(error))
            return
        self.reload()


class WeightCardSalesPage(TreasurySalesAccountingPageWithPrint):
    """Sales page supporting piece billing and actual truck-weight billing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        weight_button = QPushButton("كروت الوزن / البيع بالكيلو")
        weight_button.clicked.connect(self.open_weight_cards)
        self.layout().insertWidget(1, weight_button)

    def open_weight_cards(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        dialog = WeightCardsDialog(self.sales_repository, order_id, self)
        dialog.exec()
        self.reload_orders()


__all__ = ["WeightCardSalesPage", "WeightCardsDialog"]
