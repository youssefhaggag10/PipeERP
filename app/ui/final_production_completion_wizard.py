from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton

from app.services.material_quantity_defaults import default_actual_material_quantities
from app.ui.production_completion_wizard import ProductionCompletionWizard


class FinalProductionCompletionWizard(ProductionCompletionWizard):
    """Completion wizard with issued-quantity-aware adjustment defaults."""

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


__all__ = ["FinalProductionCompletionWizard"]
