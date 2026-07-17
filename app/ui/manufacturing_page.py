from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.repositories.manufacturing_repository import ManufacturingRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.services.manufacturing_planning_service import (
    ProductionTarget,
    calculate_batch_plan,
)

STATUS_LABELS = {
    "draft": "مسودة",
    "in_progress": "جاري التصنيع",
    "completed": "مكتمل",
    "cancelled": "ملغي",
}


class CompletionDialog(QDialog):
    def __init__(self, order: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"تسجيل الإنتاج الفعلي — {order['order_number']}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.output_inputs: dict[int, QLineEdit] = {}

        intro = QLabel(
            "سجّل العدد السليم الذي خرج فعليًا. أي زيادة ستدخل المخزون تلقائيًا، "
            "ولو العدد أقل يمكنك إلغاء النافذة وإضافة خلطة أخرى."
        )
        intro.setWordWrap(True)
        form = QFormLayout()
        for output in order["outputs"]:
            field = QLineEdit(f"{float(output['planned_quantity']):g}")
            field.setPlaceholderText("عدد المواسير السليمة")
            self.output_inputs[int(output["product_id"])] = field
            form.addRow(
                f"{output['name']} — وزن {float(output['standard_weight_kg']):g} كجم",
                field,
            )
        self.scrap_input = QLineEdit("0")
        self.scrap_input.setPlaceholderText("كجم الكسر المرتجع للمخزن")
        form.addRow("كسر المصنع الناتج (كجم)", self.scrap_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("إتمام واستلام الإنتاج")
        buttons.button(QDialogButtonBox.Cancel).setText("رجوع")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> tuple[dict[int, float], float]:
        try:
            outputs = {
                product_id: float(field.text().strip() or 0)
                for product_id, field in self.output_inputs.items()
            }
            scrap = float(self.scrap_input.text().strip() or 0)
        except ValueError as error:
            raise ValueError("الكميات الفعلية يجب أن تكون أرقامًا") from error
        return outputs, scrap


class ManufacturingPage(QWidget):
    def __init__(
        self,
        repository: ManufacturingRepository,
        product_repository: ProductRepository,
        warehouse_repository: WarehouseRepository,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.product_repository = product_repository
        self.warehouse_repository = warehouse_repository
        self.products: list[dict] = []
        self.recipes: list[dict] = []
        self.recipe_components: list[dict] = []
        self.order_outputs: list[dict] = []
        self.order_scraps: list[dict] = []
        self.orders: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("التصنيع")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "عرّف الخلطة مرة واحدة، اجمع مقاسات المواسير المطلوبة، ثم ابدأ الإنتاج بخطوات واضحة."
        )
        subtitle.setObjectName("subtitleLabel")
        tabs = QTabWidget()
        tabs.addTab(self._build_orders_tab(), "أوامر التصنيع")
        tabs.addTab(self._build_recipes_tab(), "تعريف الخلطات")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(tabs)
        self.reload()

    @staticmethod
    def _scrollable_tab(page: QWidget) -> QScrollArea:
        scroll_area = QScrollArea()
        scroll_area.setObjectName("contentScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setWidget(page)
        return scroll_area

    def _build_recipes_tab(self) -> QWidget:
        page = QWidget()
        self.recipe_code_input = QLineEdit()
        self.recipe_code_input.setPlaceholderText("مثال: IRR-A")
        self.recipe_name_input = QLineEdit()
        self.recipe_name_input.setPlaceholderText("مثال: ري ضغوط A")
        self.recipe_notes_input = QLineEdit()
        self.recipe_scrap_suggestion_input = QLineEdit("0")
        self.recipe_scrap_suggestion_input.setToolTip(
            "رقم إرشادي فقط؛ يمكن استخدام صفر أو أي كمية ومن أي مصدر داخل أمر التصنيع"
        )
        self.recipe_outputs_list = QListWidget()
        self.recipe_outputs_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.recipe_outputs_list.setMinimumHeight(110)

        header_form = QFormLayout()
        header_form.addRow("كود الخلطة", self.recipe_code_input)
        header_form.addRow("اسم عائلة الخلطة", self.recipe_name_input)
        header_form.addRow("كسر مقترح لكل خلطة (اختياري)", self.recipe_scrap_suggestion_input)
        header_form.addRow("المقاسات/المنتجات التابعة", self.recipe_outputs_list)
        header_form.addRow("ملاحظات", self.recipe_notes_input)

        self.component_product_input = QComboBox()
        self.component_qty_input = QLineEdit()
        self.component_qty_input.setPlaceholderText("كجم في الخلطة الواحدة")
        add_component = QPushButton("إضافة خامة للخلطة")
        add_component.clicked.connect(self._add_recipe_component)
        delete_component = QPushButton("حذف الخامة المحددة")
        delete_component.setObjectName("dangerButton")
        delete_component.clicked.connect(self._delete_recipe_component)
        editor = QHBoxLayout()
        editor.addWidget(QLabel("الخامة"))
        editor.addWidget(self.component_product_input, 2)
        editor.addWidget(QLabel("كجم/خلطة"))
        editor.addWidget(self.component_qty_input)
        editor.addWidget(add_component)
        editor.addWidget(delete_component)

        self.recipe_components_table = QTableWidget(0, 3)
        self.recipe_components_table.setHorizontalHeaderLabels(
            ["الكود", "الخامة", "كجم لكل خلطة"]
        )
        self.recipe_components_table.setMinimumHeight(180)
        self.recipe_components_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.recipe_components_table.setSelectionMode(QTableWidget.SingleSelection)
        self.recipe_components_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.recipe_weight_label = QLabel("وزن الخامات الأساسية: 0 كجم")
        self.recipe_weight_label.setStyleSheet("font-size: 16px; font-weight: 800;")

        save_recipe = QPushButton("حفظ الخلطة")
        save_recipe.clicked.connect(self._save_recipe)
        self.recipes_table = QTableWidget(0, 6)
        self.recipes_table.setHorizontalHeaderLabels(
            ["الكود", "الخلطة", "المقاسات المرتبطة", "الخامات كجم", "الكسر المقترح", "الإجمالي"]
        )
        self.recipes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.recipes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.recipes_table.setMinimumHeight(190)

        components_box = QGroupBox("مكونات الخلطة الأساسية")
        components_layout = QVBoxLayout(components_box)
        components_layout.addLayout(editor)
        components_layout.addWidget(self.recipe_components_table)
        components_layout.addWidget(self.recipe_weight_label)

        layout = QVBoxLayout(page)
        layout.addLayout(header_form)
        layout.addWidget(components_box)
        layout.addWidget(save_recipe)
        layout.addWidget(QLabel("الخلطات المحفوظة"))
        layout.addWidget(self.recipes_table)
        return self._scrollable_tab(page)

    def _build_orders_tab(self) -> QWidget:
        page = QWidget()
        self.order_recipe_input = QComboBox()
        self.order_recipe_input.currentIndexChanged.connect(self._recipe_selected)
        self.order_warehouse_input = QComboBox()
        self.order_notes_input = QLineEdit()
        top_form = QFormLayout()
        top_form.addRow("عائلة الخلطة", self.order_recipe_input)
        top_form.addRow("المخزن", self.order_warehouse_input)
        top_form.addRow("ملاحظات التشغيل", self.order_notes_input)

        self.output_product_input = QComboBox()
        self.output_qty_input = QLineEdit()
        self.output_qty_input.setPlaceholderText("عدد المواسير المطلوبة")
        add_output = QPushButton("إضافة المقاس")
        add_output.clicked.connect(self._add_order_output)
        remove_output = QPushButton("حذف المقاس")
        remove_output.setObjectName("dangerButton")
        remove_output.clicked.connect(self._delete_order_output)
        output_editor = QHBoxLayout()
        output_editor.addWidget(QLabel("المقاس/الصنف"))
        output_editor.addWidget(self.output_product_input, 2)
        output_editor.addWidget(QLabel("العدد"))
        output_editor.addWidget(self.output_qty_input)
        output_editor.addWidget(add_output)
        output_editor.addWidget(remove_output)
        self.outputs_table = QTableWidget(0, 4)
        self.outputs_table.setHorizontalHeaderLabels(
            ["الصنف", "العدد المطلوب", "وزن الماسورة كجم", "إجمالي الوزن كجم"]
        )
        self.outputs_table.setMinimumHeight(160)
        self.outputs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.scrap_product_input = QComboBox()
        self.scrap_qty_input = QLineEdit()
        self.scrap_qty_input.setPlaceholderText("كجم لكل خلطة — اتركه بلا كسر لو غير متاح")
        add_scrap = QPushButton("استخدام الكسر")
        add_scrap.clicked.connect(self._add_order_scrap)
        remove_scrap = QPushButton("حذف الكسر")
        remove_scrap.setObjectName("dangerButton")
        remove_scrap.clicked.connect(self._delete_order_scrap)
        scrap_editor = QHBoxLayout()
        scrap_editor.addWidget(QLabel("مصدر الكسر"))
        scrap_editor.addWidget(self.scrap_product_input, 2)
        scrap_editor.addWidget(QLabel("كجم/خلطة"))
        scrap_editor.addWidget(self.scrap_qty_input)
        scrap_editor.addWidget(add_scrap)
        scrap_editor.addWidget(remove_scrap)
        self.scraps_table = QTableWidget(0, 4)
        self.scraps_table.setHorizontalHeaderLabels(
            ["مصدر الكسر", "المتاح كجم", "المستخدم/خلطة", "الإجمالي بعد الحساب"]
        )
        self.scraps_table.setMinimumHeight(160)
        self.scraps_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.plan_label = QLabel("أضف المقاسات المطلوبة لعرض خطة التشغيل")
        self.plan_label.setWordWrap(True)
        self.plan_label.setStyleSheet(
            "font-size: 17px; font-weight: 800; padding: 12px; "
            "background: #0F2A4A; border-radius: 8px;"
        )
        save_order = QPushButton("إنشاء أمر التصنيع كمسودة")
        save_order.clicked.connect(self._save_order)

        outputs_box = QGroupBox("1 — المواسير المطلوبة")
        outputs_layout = QVBoxLayout(outputs_box)
        outputs_layout.addLayout(output_editor)
        outputs_layout.addWidget(self.outputs_table)
        scrap_box = QGroupBox("2 — كسر المصنع الاختياري (من أي مصدر)")
        scrap_layout = QVBoxLayout(scrap_box)
        scrap_layout.addLayout(scrap_editor)
        scrap_layout.addWidget(self.scraps_table)

        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر", "الخلطة", "المطلوب", "المخطط", "الفعلي",
                "الحالة", "تكلفة الخامات", "فرق الوزن",
            ]
        )
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.orders_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SingleSelection)
        self.orders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.orders_table.setMinimumHeight(210)
        start = QPushButton("بدء وصرف الخامات")
        start.clicked.connect(self._start_selected)
        add_batch = QPushButton("إضافة خلطة للأمر الجاري")
        add_batch.clicked.connect(self._add_batch_selected)
        complete = QPushButton("تسجيل الناتج وإتمام الأمر")
        complete.clicked.connect(self._complete_selected)
        actions = QHBoxLayout()
        actions.addWidget(start)
        actions.addWidget(add_batch)
        actions.addWidget(complete)
        actions.addStretch()

        layout = QVBoxLayout(page)
        layout.addLayout(top_form)
        layout.addWidget(outputs_box)
        layout.addWidget(scrap_box)
        layout.addWidget(self.plan_label)
        layout.addWidget(save_order)
        layout.addWidget(QLabel("أوامر التصنيع"))
        layout.addLayout(actions)
        layout.addWidget(self.orders_table)
        return self._scrollable_tab(page)

    def reload(self) -> None:
        self.products = self.product_repository.list_products()
        self.recipes = self.repository.list_recipes()
        selected_recipe = self.order_recipe_input.currentData()
        selected_warehouse = self.order_warehouse_input.currentData()

        self.recipe_outputs_list.clear()
        self.component_product_input.clear()
        for product in self.products:
            if product["product_type"] == "finished_good":
                label = (
                    f"{product['code']} — {product['name']} "
                    f"({float(product.get('standard_weight_kg', 0)):g} كجم)"
                )
                self.recipe_outputs_list.addItem(label)
                self.recipe_outputs_list.item(self.recipe_outputs_list.count() - 1).setData(
                    Qt.UserRole, int(product["id"])
                )
            if product["product_type"] == "raw_material":
                self.component_product_input.addItem(
                    f"{product['code']} — {product['name']}", int(product["id"])
                )

        self.order_recipe_input.blockSignals(True)
        self.order_recipe_input.clear()
        for recipe in self.recipes:
            self.order_recipe_input.addItem(
                f"{recipe['code']} — {recipe['name']}", int(recipe["id"])
            )
        self.order_recipe_input.blockSignals(False)
        if selected_recipe is not None:
            index = self.order_recipe_input.findData(selected_recipe)
            if index >= 0:
                self.order_recipe_input.setCurrentIndex(index)

        self.order_warehouse_input.clear()
        for warehouse in self.warehouse_repository.list_warehouses():
            self.order_warehouse_input.addItem(warehouse["name"], int(warehouse["id"]))
        if selected_warehouse is not None:
            index = self.order_warehouse_input.findData(selected_warehouse)
            if index >= 0:
                self.order_warehouse_input.setCurrentIndex(index)
        self._reload_recipes_table()
        self._recipe_selected()
        self._reload_orders()

    def _add_recipe_component(self) -> None:
        if self.component_product_input.currentData() is None:
            return
        try:
            quantity = float(self.component_qty_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "كمية الخامة يجب أن تكون رقمًا")
            return
        if quantity <= 0:
            QMessageBox.warning(self, "تنبيه", "كمية الخامة يجب أن تكون أكبر من صفر")
            return
        product_id = int(self.component_product_input.currentData())
        product = next(item for item in self.products if int(item["id"]) == product_id)
        self.recipe_components.append(
            {
                "product_id": product_id,
                "code": product["code"],
                "name": product["name"],
                "quantity_per_batch": quantity,
            }
        )
        self.component_qty_input.clear()
        self._refresh_recipe_components()
        last_row = self.recipe_components_table.rowCount() - 1
        if last_row >= 0:
            self.recipe_components_table.setCurrentCell(last_row, 0)
            item = self.recipe_components_table.item(last_row, 0)
            if item is not None:
                self.recipe_components_table.scrollToItem(
                    item,
                    QAbstractItemView.PositionAtCenter,
                )

    def _delete_recipe_component(self) -> None:
        row = self.recipe_components_table.currentRow()
        if 0 <= row < len(self.recipe_components):
            del self.recipe_components[row]
            self._refresh_recipe_components()

    def _refresh_recipe_components(self) -> None:
        self.recipe_components_table.setRowCount(len(self.recipe_components))
        for row_index, component in enumerate(self.recipe_components):
            for column, value in enumerate(
                [
                    component["code"], component["name"],
                    f"{float(component['quantity_per_batch']):g}",
                ]
            ):
                self.recipe_components_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        total = sum(float(row["quantity_per_batch"]) for row in self.recipe_components)
        self.recipe_weight_label.setText(f"وزن الخامات الأساسية: {total:g} كجم لكل خلطة")

    def _save_recipe(self) -> None:
        output_ids = [
            int(item.data(Qt.UserRole)) for item in self.recipe_outputs_list.selectedItems()
        ]
        try:
            recipe_id = self.repository.create_recipe(
                code=self.recipe_code_input.text(),
                name=self.recipe_name_input.text(),
                output_product_ids=output_ids,
                components=self.recipe_components,
                suggested_scrap_per_batch=float(
                    self.recipe_scrap_suggestion_input.text().strip() or 0
                ),
                notes=self.recipe_notes_input.text(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.recipe_code_input.clear()
        self.recipe_name_input.clear()
        self.recipe_notes_input.clear()
        self.recipe_scrap_suggestion_input.setText("0")
        self.recipe_components.clear()
        self._refresh_recipe_components()
        self.reload()
        QMessageBox.information(self, "تم", f"تم حفظ الخلطة رقم {recipe_id}")

    def _reload_recipes_table(self) -> None:
        self.recipes_table.setRowCount(len(self.recipes))
        for row_index, recipe in enumerate(self.recipes):
            base = float(recipe["base_batch_weight"])
            scrap = float(recipe["suggested_scrap_per_batch"])
            values = [
                recipe["code"], recipe["name"], recipe["output_summary"],
                f"{base:g}", f"{scrap:g}", f"{base + scrap:g}",
            ]
            for column, value in enumerate(values):
                self.recipes_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _recipe_selected(self) -> None:
        self.output_product_input.clear()
        self.scrap_product_input.clear()
        recipe_id = self.order_recipe_input.currentData()
        warehouse_id = self.order_warehouse_input.currentData()
        if recipe_id is None:
            return
        recipe = self.repository.get_recipe(int(recipe_id))
        for output in recipe["outputs"]:
            output_label = (
                f"{output['code']} — {output['name']} "
                f"({float(output['standard_weight_kg']):g} كجم)"
            )
            self.output_product_input.addItem(
                output_label,
                int(output["product_id"]),
            )
        if warehouse_id is not None:
            for scrap in self.repository.list_scrap_stock(int(warehouse_id)):
                self.scrap_product_input.addItem(
                    f"{scrap['name']} — متاح {float(scrap['available']):g} كجم",
                    int(scrap["product_id"]),
                )
                index = self.scrap_product_input.count() - 1
                self.scrap_product_input.setItemData(
                    index, float(scrap["available"]), Qt.UserRole + 1
                )
        self.order_outputs.clear()
        self.order_scraps.clear()
        self._refresh_order_lines()

    def _add_order_output(self) -> None:
        product_id = self.output_product_input.currentData()
        if product_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر خلطة لها مقاسات مرتبطة")
            return
        try:
            quantity = float(self.output_qty_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "عدد المواسير يجب أن يكون رقمًا")
            return
        if quantity <= 0:
            QMessageBox.warning(self, "تنبيه", "عدد المواسير يجب أن يكون أكبر من صفر")
            return
        recipe = self.repository.get_recipe(int(self.order_recipe_input.currentData()))
        output = next(
            row for row in recipe["outputs"] if int(row["product_id"]) == int(product_id)
        )
        self.order_outputs = [
            row for row in self.order_outputs if int(row["product_id"]) != int(product_id)
        ]
        self.order_outputs.append(
            {
                "product_id": int(product_id),
                "name": output["name"],
                "quantity": quantity,
                "standard_weight_kg": float(output["standard_weight_kg"]),
            }
        )
        self.output_qty_input.clear()
        self._refresh_order_lines()

    def _delete_order_output(self) -> None:
        row = self.outputs_table.currentRow()
        if 0 <= row < len(self.order_outputs):
            del self.order_outputs[row]
            self._refresh_order_lines()

    def _add_order_scrap(self) -> None:
        product_id = self.scrap_product_input.currentData()
        if product_id is None:
            QMessageBox.warning(self, "تنبيه", "لا يوجد كسر متاح؛ يمكنك التصنيع من غيره")
            return
        try:
            quantity = float(self.scrap_qty_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "كمية الكسر يجب أن تكون رقمًا")
            return
        if quantity <= 0:
            QMessageBox.warning(self, "تنبيه", "كمية الكسر يجب أن تكون أكبر من صفر")
            return
        index = self.scrap_product_input.currentIndex()
        available = float(self.scrap_product_input.itemData(index, Qt.UserRole + 1) or 0)
        name = self.scrap_product_input.currentText().split(" — متاح")[0]
        self.order_scraps = [
            row for row in self.order_scraps if int(row["product_id"]) != int(product_id)
        ]
        self.order_scraps.append(
            {
                "product_id": int(product_id), "name": name,
                "available": available, "quantity_per_batch": quantity,
            }
        )
        self.scrap_qty_input.clear()
        self._refresh_order_lines()

    def _delete_order_scrap(self) -> None:
        row = self.scraps_table.currentRow()
        if 0 <= row < len(self.order_scraps):
            del self.order_scraps[row]
            self._refresh_order_lines()

    def _current_plan(self):
        if not self.order_outputs or self.order_recipe_input.currentData() is None:
            return None
        recipe = self.repository.get_recipe(int(self.order_recipe_input.currentData()))
        material_quantities = [
            float(row["quantity_per_batch"])
            for row in recipe["components"]
            if row["component_kind"] == "material"
        ]
        return calculate_batch_plan(
            [
                ProductionTarget(
                    int(row["product_id"]), float(row["quantity"]),
                    float(row["standard_weight_kg"]),
                )
                for row in self.order_outputs
            ],
            material_quantities,
            [float(row["quantity_per_batch"]) for row in self.order_scraps],
        )

    def _refresh_order_lines(self) -> None:
        self.outputs_table.setRowCount(len(self.order_outputs))
        for row_index, output in enumerate(self.order_outputs):
            values = [
                output["name"], f"{float(output['quantity']):g}",
                f"{float(output['standard_weight_kg']):g}",
                f"{float(output['quantity']) * float(output['standard_weight_kg']):g}",
            ]
            for column, value in enumerate(values):
                self.outputs_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        plan = self._current_plan()
        self.scraps_table.setRowCount(len(self.order_scraps))
        for row_index, scrap in enumerate(self.order_scraps):
            total = float(scrap["quantity_per_batch"]) * (plan.batches if plan else 0)
            values = [
                scrap["name"], f"{float(scrap['available']):g}",
                f"{float(scrap['quantity_per_batch']):g}", f"{total:g}",
            ]
            for column, value in enumerate(values):
                self.scraps_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        if plan is None:
            self.plan_label.setText("أضف المقاسات المطلوبة لعرض خطة التشغيل")
            return
        shortage = [
            row for row in self.order_scraps
            if float(row["quantity_per_batch"]) * plan.batches > float(row["available"])
        ]
        warning = (
            "\n⚠ الكسر أقل من المخطط؛ النظام سيصرف المتاح فقط ولن يوقف التصنيع."
            if shortage
            else ""
        )
        self.plan_label.setText(
            f"الوزن المطلوب: {plan.target_weight:,.2f} كجم  |  "
            f"وزن الخلطة: {plan.batch_weight:,.2f} كجم  |  "
            f"عدد الخلطات: {plan.batches}  |  "
            f"الداخل المخطط: {plan.planned_input_weight:,.2f} كجم  |  "
            f"الزيادة المتوقعة: {plan.expected_overage_weight:,.2f} كجم{warning}"
        )

    def _save_order(self) -> None:
        recipe_id = self.order_recipe_input.currentData()
        warehouse_id = self.order_warehouse_input.currentData()
        if recipe_id is None or warehouse_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر الخلطة والمخزن")
            return
        plan = self._current_plan()
        if plan is None:
            QMessageBox.warning(self, "تنبيه", "أضف المواسير المطلوبة")
            return
        try:
            order_id = self.repository.create_order(
                recipe_id=int(recipe_id), warehouse_id=int(warehouse_id),
                outputs=self.order_outputs, scrap_inputs=self.order_scraps,
                notes=self.order_notes_input.text(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.order_outputs.clear()
        self.order_scraps.clear()
        self.order_notes_input.clear()
        self._refresh_order_lines()
        self._reload_orders()
        QMessageBox.information(self, "تم", f"تم إنشاء أمر التصنيع رقم {order_id} كمسودة")

    def _selected_order_id(self) -> int | None:
        row = self.orders_table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختر أمر تصنيع من الجدول")
            return None
        return int(self.orders[row]["id"])

    def _start_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            self.repository.start_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر البدء", str(error))
            return
        self._reload_orders()
        QMessageBox.information(self, "تم", "تم صرف الخامات وبدء أمر التصنيع")

    def _add_batch_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            self.repository.add_batch(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر إضافة الخلطة", str(error))
            return
        self._reload_orders()
        QMessageBox.information(self, "تم", "تم صرف خامات خلطة إضافية")

    def _complete_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            order = self.repository.get_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        dialog = CompletionDialog(order, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            outputs, scrap = dialog.values()
            result = self.repository.complete_order(
                order_id, actual_outputs=outputs, returned_scrap_quantity=scrap
            )
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الإتمام", str(error))
            return
        self._reload_orders()
        QMessageBox.information(
            self,
            "تم استلام الإنتاج",
            f"تكلفة الإنتاج التام: {result['finished_cost']:,.2f}\n"
            f"تكلفة كجم الكسر: {result['scrap_unit_cost']:,.4f}\n"
            f"فرق الوزن الرقابي: {result['weight_variance']:,.2f} كجم",
        )

    def _reload_orders(self) -> None:
        self.orders = self.repository.list_orders()
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            values = [
                order["order_number"], order["recipe_name"], order["output_summary"],
                order["planned_batches"], order["actual_batches"],
                STATUS_LABELS.get(str(order["status"]), order["status"]),
                f"{float(order['material_cost']):,.2f}",
                f"{float(order['weight_variance']):,.2f}",
            ]
            for column, value in enumerate(values):
                self.orders_table.setItem(row_index, column, QTableWidgetItem(str(value)))
