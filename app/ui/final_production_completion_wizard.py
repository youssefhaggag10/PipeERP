from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QPushButton

from app.services.completion_scrap_calculator import calculate_suggested_scrap_weight
from app.services.material_quantity_defaults import default_actual_material_quantities
from app.ui.production_completion_wizard import ProductionCompletionWizard


class FinalProductionCompletionWizard(ProductionCompletionWizard):
    """Aggregate completion with automatic scrap and issued-aware defaults."""

    def __init__(self, order: dict, parent=None) -> None:
        self._manual_weight_products: set[int] = set()
        super().__init__(order, parent)
        self._remove_defective_output_controls()
        self._connect_automatic_scrap_calculation()
        self.recalculate_scrap()

    def _remove_defective_output_controls(self) -> None:
        # Defective production is recorded as factory scrap, not as a separate output.
        self.outputs_table.setColumnHidden(2, True)
        for _product_id, (_good, defective, _weight) in self.output_inputs.items():
            defective.setText("0")
            defective.setReadOnly(True)

        summary_value = self.summary_labels.get("defective_output_quantity")
        if summary_value is None:
            return
        summary_value.hide()
        parent = summary_value.parentWidget()
        layout = parent.layout() if parent is not None else None
        if isinstance(layout, QFormLayout):
            label = layout.labelForField(summary_value)
            if label is not None:
                label.hide()

    def _connect_automatic_scrap_calculation(self) -> None:
        self.scrap_input.setPlaceholderText("يُحسب تلقائيًا من الخامات والإنتاج")
        self.scrap_input.setToolTip(
            "يتحدث الكسر تلقائيًا عند تغيير عدد الخلطات أو عدد/وزن المواسير، "
            "ويمكن تعديله يدويًا بعد المراجعة."
        )
        self.actual_batches_input.textChanged.connect(self.recalculate_scrap)
        self.modified_radio.toggled.connect(self.recalculate_scrap)
        self.all_complete_radio.toggled.connect(self.recalculate_scrap)

        output_by_id = {
            int(output["product_id"]): output for output in self.order["outputs"]
        }
        for product_id, (good, _defective, actual_weight) in self.output_inputs.items():
            standard_weight = float(
                output_by_id.get(product_id, {}).get("standard_weight_kg", 0) or 0
            )
            actual_weight.setProperty("pipeerp_standard_weight", standard_weight)
            good.textChanged.connect(
                lambda text, current_product_id=product_id: self._good_quantity_changed(
                    current_product_id, text
                )
            )
            actual_weight.textEdited.connect(
                lambda text, current_product_id=product_id: self._actual_weight_edited(
                    current_product_id, text
                )
            )
            actual_weight.textChanged.connect(self.recalculate_scrap)

    def _actual_weight_edited(self, product_id: int, text: str) -> None:
        if text.strip():
            self._manual_weight_products.add(product_id)
        else:
            self._manual_weight_products.discard(product_id)
        self.recalculate_scrap()

    def _good_quantity_changed(self, product_id: int, text: str) -> None:
        if product_id in self._manual_weight_products:
            self.recalculate_scrap()
            return
        fields = self.output_inputs.get(product_id)
        if fields is None:
            return
        _good, _defective, actual_weight = fields
        try:
            quantity = float(text.strip() or 0)
            standard_weight = float(actual_weight.property("pipeerp_standard_weight") or 0)
        except (TypeError, ValueError):
            self.recalculate_scrap()
            return
        with QSignalBlocker(actual_weight):
            actual_weight.setText(f"{max(0.0, quantity) * standard_weight:g}")
        self.recalculate_scrap()

    def _safe_adjustments_for_scrap(self) -> list[dict]:
        if not self.modified_radio.isChecked():
            return []
        adjustments: list[dict] = []
        for row in range(self.adjustments_table.rowCount()):
            batch_input = self.adjustments_table.cellWidget(row, 0)
            material_input = self.adjustments_table.cellWidget(row, 1)
            if not isinstance(batch_input, QLineEdit) or not isinstance(
                material_input, QComboBox
            ):
                continue
            try:
                batch_count = int(batch_input.text().strip())
            except ValueError:
                continue
            excluded_product_id = material_input.currentData()
            if batch_count <= 0 or excluded_product_id is None:
                continue
            adjustments.append(
                {
                    "excluded_product_id": int(excluded_product_id),
                    "batch_count": batch_count,
                    "actual_material_quantities": self.adjustment_quantities.get(row, {}),
                }
            )
        return adjustments

    def recalculate_scrap(self, *_args) -> None:
        try:
            actual_batches = int(self.actual_batches_input.text().strip())
            output_weights = {
                product_id: float(fields[2].text().strip() or 0)
                for product_id, fields in self.output_inputs.items()
            }
            suggested = calculate_suggested_scrap_weight(
                materials=self.materials,
                actual_batches=actual_batches,
                issued_batches=int(self.order.get("actual_batches", 0) or 0),
                output_weights=output_weights,
                adjustments=self._safe_adjustments_for_scrap(),
            )
        except (TypeError, ValueError):
            return
        with QSignalBlocker(self.scrap_input):
            self.scrap_input.setText(f"{suggested:g}")

    def add_adjustment_row(self) -> None:
        super().add_adjustment_row()
        row = self.adjustments_table.rowCount() - 1
        batch_input = self.adjustments_table.cellWidget(row, 0)
        material_input = self.adjustments_table.cellWidget(row, 1)
        if isinstance(batch_input, QLineEdit):
            batch_input.textChanged.connect(self.recalculate_scrap)
        if isinstance(material_input, QComboBox):
            material_input.currentIndexChanged.connect(self.recalculate_scrap)
        self.recalculate_scrap()

    def remove_adjustment_row(self) -> None:
        super().remove_adjustment_row()
        self.recalculate_scrap()

    def edit_quantities(self, button: QPushButton) -> None:
        row = next(
            (
                index
                for index in range(self.adjustments_table.rowCount())
                if self.adjustments_table.cellWidget(index, 3) is button
            ),
            -1,
        )
        if row >= 0 and not self.adjustment_quantities.get(row):
            batch_input = self.adjustments_table.cellWidget(row, 0)
            material_input = self.adjustments_table.cellWidget(row, 1)
            if isinstance(batch_input, QLineEdit) and isinstance(material_input, QComboBox):
                try:
                    batch_count = int(batch_input.text().strip())
                except ValueError:
                    batch_count = 0
                excluded_product_id = material_input.currentData()
                if batch_count > 0 and excluded_product_id is not None:
                    self.adjustment_quantities[row] = default_actual_material_quantities(
                        self.materials,
                        excluded_product_id=int(excluded_product_id),
                        batch_count=batch_count,
                        issued_batches=int(self.order.get("actual_batches", 0) or 0),
                    )
        super().edit_quantities(button)
        self.recalculate_scrap()


__all__ = ["FinalProductionCompletionWizard"]
