from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.replanned_manufacturing_page import ReplannedManufacturingPage

RUN_STATUS = {
    "draft": "جاهزة للصرف",
    "in_progress": "جارية",
    "completed": "مكتملة",
    "stopped": "متوقفة",
    "cancelled": "ملغاة",
}


class RunCompletionDialog(QDialog):
    def __init__(self, repository, run: dict, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.run = run
        self.output_inputs: dict[int, tuple[QLineEdit, QLineEdit]] = {}
        self.setWindowTitle(f"إغلاق خلطة التشغيل رقم {run['run_number']} وتسجيل الإنتاج")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(720, 520)

        intro = QLabel(
            "أدخل عدد المواسير السليمة والوزن الفعلي الإجمالي لكل مقاس. "
            "الوزن القياسي يظهر للمراجعة فقط، أما التكلفة والمخزون الوزني فيعتمدان "
            "على الوزن الفعلي المسجل هنا."
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        for output in run["outputs"]:
            quantity = QLineEdit("0")
            quantity.setPlaceholderText("عدد المواسير السليمة")
            actual_weight = QLineEdit("0")
            actual_weight.setPlaceholderText("الوزن الفعلي الإجمالي بالكيلو")
            row = QHBoxLayout()
            row.addWidget(QLabel("العدد"))
            row.addWidget(quantity, 1)
            row.addWidget(QLabel("الوزن الفعلي كجم"))
            row.addWidget(actual_weight, 1)
            standard = float(output.get("standard_weight_kg", 0) or 0)
            form.addRow(
                f"{output['code']} — {output['name']} — قياسي {standard:g} كجم",
                row,
            )
            self.output_inputs[int(output["product_id"])] = (quantity, actual_weight)

        self.scrap_input = QLineEdit("0")
        self.scrap_input.setPlaceholderText("وزن الكسر أو الهالك المرتجع بالكيلو")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("ملاحظات نتيجة الخلطة أو سبب المشكلة")
        form.addRow("الكسر/الهالك الناتج كجم", self.scrap_input)
        form.addRow("ملاحظات", self.notes_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("إغلاق الخلطة واستلام الإنتاج")
        buttons.button(QDialogButtonBox.Cancel).setText("رجوع")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[dict[int, dict[str, float]], float, str]:
        outputs: dict[int, dict[str, float]] = {}
        try:
            for product_id, (quantity_field, weight_field) in self.output_inputs.items():
                outputs[product_id] = {
                    "quantity": float(quantity_field.text().strip() or 0),
                    "actual_weight_kg": float(weight_field.text().strip() or 0),
                }
            scrap = float(self.scrap_input.text().strip() or 0)
        except ValueError as error:
            raise ValueError("العدد والوزن الفعلي والكسر يجب أن تكون أرقامًا") from error
        return outputs, scrap, self.notes_input.text().strip()


class ProductionRunsDialog(QDialog):
    def __init__(self, repository, order_id: int, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.order_id = int(order_id)
        self.runs: list[dict] = []
        self.setWindowTitle("خلطات تشغيل أمر التصنيع")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1180, 720)

        explanation = QLabel(
            "كل صف يمثل خلطة فعلية تم تجهيزها ووضعها في الماكينة. يمكن إغلاق "
            "الخلطة التي ظهرت فيها مشكلة ثم إنشاء خلطة جديدة من السابقة بعد حذف "
            "الخامة المسببة للمشكلة، دون تغيير تكلفة الإنتاج السابق."
        )
        explanation.setWordWrap(True)

        self.runs_table = QTableWidget(0, 10)
        self.runs_table.setHorizontalHeaderLabels(
            [
                "رقم الخلطة",
                "الحالة",
                "عدد الدفعات المصروفة",
                "وزن الداخل",
                "تكلفة الخامات",
                "وزن الإنتاج السليم",
                "وزن الكسر",
                "تكلفة الإنتاج",
                "سبب التغيير",
                "الملاحظات",
            ]
        )
        self.runs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.runs_table.setSelectionMode(QTableWidget.SingleSelection)
        self.runs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.runs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.runs_table.horizontalHeader().setStretchLastSection(True)
        self.runs_table.itemSelectionChanged.connect(self._reload_materials)

        self.materials_table = QTableWidget(0, 7)
        self.materials_table.setHorizontalHeaderLabels(
            [
                "الكود",
                "الخامة",
                "النوع",
                "لكل دفعة كجم",
                "المصروف فعليًا",
                "سعر الوحدة",
                "التكلفة",
            ]
        )
        self.materials_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.materials_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        ensure_button = QPushButton("إنشاء/فتح الخلطة الحالية")
        ensure_button.clicked.connect(self.ensure_run)
        issue_button = QPushButton("صرف خامات الخلطة المحددة")
        issue_button.clicked.connect(self.issue_selected)
        complete_button = QPushButton("إغلاق الخلطة وتسجيل إنتاجها")
        complete_button.clicked.connect(self.complete_selected)
        clone_button = QPushButton("خلطة جديدة من السابقة بدون خامة")
        clone_button.setObjectName("secondaryButton")
        clone_button.clicked.connect(self.clone_without_material)
        close_order_button = QPushButton("إتمام أمر التصنيع من الخلطات المكتملة")
        close_order_button.clicked.connect(self.close_order)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)

        actions = QHBoxLayout()
        for button in (
            ensure_button,
            issue_button,
            complete_button,
            clone_button,
            close_order_button,
            refresh_button,
        ):
            actions.addWidget(button)
        actions.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("إغلاق")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(explanation)
        layout.addLayout(actions)
        layout.addWidget(QLabel("خلطات التشغيل"))
        layout.addWidget(self.runs_table, 3)
        layout.addWidget(QLabel("خامات الخلطة المحددة"))
        layout.addWidget(self.materials_table, 2)
        layout.addWidget(buttons)
        self.reload()

    def reload(self) -> None:
        self.runs = self.repository.list_runs(self.order_id)
        self.runs_table.setRowCount(len(self.runs))
        for row_index, run in enumerate(self.runs):
            values = [
                run["run_number"],
                RUN_STATUS.get(str(run["status"]), run["status"]),
                run["issued_batches"],
                f"{float(run['actual_input_weight']):,.3f}",
                f"{float(run['material_cost']):,.2f}",
                f"{float(run['good_output_weight']):,.3f}",
                f"{float(run['scrap_weight']):,.3f}",
                f"{float(run['finished_cost']):,.2f}",
                run.get("change_reason", "") or "",
                run.get("notes", "") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(run["id"]))
                self.runs_table.setItem(row_index, column, item)
        if self.runs:
            self.runs_table.selectRow(len(self.runs) - 1)
        else:
            self.materials_table.setRowCount(0)

    def _selected_run_id(self) -> int | None:
        row = self.runs_table.currentRow()
        if row < 0 or row >= len(self.runs):
            QMessageBox.warning(self, "تنبيه", "اختر خلطة تشغيل من الجدول")
            return None
        return int(self.runs[row]["id"])

    def _reload_materials(self) -> None:
        row = self.runs_table.currentRow()
        if row < 0 or row >= len(self.runs):
            self.materials_table.setRowCount(0)
            return
        run = self.repository.get_run(int(self.runs[row]["id"]))
        materials = run["materials"]
        self.materials_table.setRowCount(len(materials))
        for row_index, material in enumerate(materials):
            values = [
                material["code"],
                material["name"],
                "كسر اختياري" if material["component_kind"] == "scrap" else "خامة أساسية",
                f"{float(material['quantity_per_batch']):,.3f}",
                f"{float(material['actual_quantity']):,.3f}",
                f"{float(material['unit_cost']):,.4f}",
                f"{float(material['total_cost']):,.2f}",
            ]
            for column, value in enumerate(values):
                self.materials_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def ensure_run(self) -> None:
        try:
            self.repository.ensure_current_run(self.order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر إنشاء الخلطة", str(error))
            return
        self.reload()

    def issue_selected(self) -> None:
        run_id = self._selected_run_id()
        if run_id is None:
            return
        batches, accepted = QInputDialog.getInt(
            self,
            "عدد الدفعات",
            "كم دفعة من هذه الخلطة سيتم تجهيزها وصرف خاماتها الآن؟",
            1,
            1,
            1000,
        )
        if not accepted:
            return
        try:
            result = self.repository.issue_run(run_id, batches)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الصرف", str(error))
            return
        self.reload()
        QMessageBox.information(
            self,
            "تم صرف الخلطة",
            f"وزن الخامات المصروفة: {result['input_weight']:,.3f} كجم\n"
            f"تكلفتها الفعلية: {result['material_cost']:,.2f}",
        )

    def complete_selected(self) -> None:
        run_id = self._selected_run_id()
        if run_id is None:
            return
        try:
            run = self.repository.get_run(run_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        dialog = RunCompletionDialog(self.repository, run, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            outputs, scrap, notes = dialog.values()
            result = self.repository.complete_run(
                run_id,
                outputs=outputs,
                scrap_weight=scrap,
                notes=notes,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تعذر إغلاق الخلطة", str(error))
            return
        self.reload()
        QMessageBox.information(
            self,
            "تم تسجيل إنتاج الخلطة",
            f"وزن الإنتاج السليم: {result['good_output_weight']:,.3f} كجم\n"
            f"تكلفة الإنتاج: {result['finished_cost']:,.2f}\n"
            f"فرق الوزن الرقابي: {result['weight_variance']:,.3f} كجم",
        )

    def clone_without_material(self) -> None:
        run_id = self._selected_run_id()
        if run_id is None:
            return
        run = self.repository.get_run(run_id)
        materials = [item for item in run["materials"] if item["component_kind"] != "scrap"]
        if not materials:
            QMessageBox.warning(self, "تنبيه", "لا توجد خامات أساسية في الخلطة")
            return
        labels = [f"{item['code']} — {item['name']}" for item in materials]
        selected, accepted = QInputDialog.getItem(
            self,
            "الخامة المسببة للمشكلة",
            "اختر الخامة التي لن تدخل في الخلطة الجديدة:",
            labels,
            0,
            False,
        )
        if not accepted:
            return
        material = materials[labels.index(selected)]
        reason, accepted = QInputDialog.getMultiLineText(
            self,
            "سبب تعديل الخلطة",
            "اكتب وصف المشكلة وسبب حذف الخامة:",
        )
        if not accepted:
            return
        try:
            new_run_id = self.repository.clone_run_without_material(
                self.order_id,
                run_id,
                int(material["product_id"]),
                reason,
            )
            new_run = self.repository.get_run(new_run_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر إنشاء الخلطة الجديدة", str(error))
            return
        self.reload()
        QMessageBox.information(
            self,
            "تم إنشاء خلطة جديدة",
            f"تم إنشاء خلطة تشغيل جديدة رقم {new_run['run_number']} بدون {material['name']}.\n"
            "الإنتاج السابق وتكلفته لم يتغيرا.",
        )

    def close_order(self) -> None:
        answer = QMessageBox.question(
            self,
            "تأكيد إتمام أمر التصنيع",
            "سيجمع النظام نتائج وتكاليف كل خلطات التشغيل المكتملة ويغلق أمر التصنيع. "
            "هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            summary = self.repository.close_order_from_runs(self.order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الإتمام", str(error))
            return
        QMessageBox.information(
            self,
            "تم إتمام أمر التصنيع",
            f"عدد الخلطات المكتملة: {int(summary['run_count'])}\n"
            f"وزن الإنتاج السليم: {float(summary['good_weight']):,.3f} كجم\n"
            f"تكلفة الإنتاج: {float(summary['finished_cost']):,.2f}",
        )
        self.accept()


class ProductionRunManufacturingPage(ReplannedManufacturingPage):
    """Manufacturing page driven by physical operating mixes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        run_button = QPushButton("خلطات تشغيل أمر التصنيع")
        run_button.clicked.connect(self.open_production_runs)
        page = self.orders_table.parentWidget()
        if page is not None and page.layout() is not None:
            page.layout().insertWidget(max(0, page.layout().count() - 1), run_button)

    def open_production_runs(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            order = self.repository.get_order(order_id)
            if str(order["status"]) == "draft":
                answer = QMessageBox.question(
                    self,
                    "بدء أمر التصنيع",
                    "سيتم بدء الأمر بدون صرف كل الخامات مقدمًا. الصرف سيكون لكل "
                    "خلطة تشغيل عند تجهيزها. هل تريد المتابعة؟",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
                self.repository.start_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر فتح الخلطات", str(error))
            return
        dialog = ProductionRunsDialog(self.repository, order_id, self)
        dialog.exec()
        self._reload_orders()

    def _start_selected(self) -> None:
        self.open_production_runs()

    def _complete_selected(self) -> None:
        self.open_production_runs()


__all__ = [
    "ProductionRunManufacturingPage",
    "ProductionRunsDialog",
    "RunCompletionDialog",
]
