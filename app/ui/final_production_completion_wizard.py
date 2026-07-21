from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton

from app.ui.production_completion_wizard import ProductionCompletionWizard


def default_actual_material_quantities(
    materials: list[dict],
    *,
    excluded_product_id: int,
    batch_count: int,
    issued_batches: int,
) -> dict[int, float]:
    """Build safe defaults from the quantities that were actually issued.

    Raw materials keep their recipe quantity per batch. Optional scrap is capped
    by the quantity issued per batch so opening the details dialog cannot create
    an artificial over-consumption error.
    """
    batch_count = int(batch_count)
    issued_batches = max(1, int(issued_batches))
    if batch_count <= 0:
        return {}

    defaults: dict[int, float] = {}
    for material in materials:
        product_id = int(material["product_id"])
        if product_id == int(excluded_product_id):
            continue

        quantity_per_batch = float(material.get("quantity_per_batch", 0) or 0)
        if str(material.get("component_kind", "material")) == "scrap":
            issued_quantity = float(material.get("actual_quantity", 0) or 0)
            quantity_per_batch = min(
                quantity_per_batch,
                issued_quantity / issued_batches,
            )
        defaults[product_id] = quantity_per_batch * batch_count
    return defaults


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


__all__ = [
    "FinalProductionCompletionWizard",
    "default_actual_material_quantities",
]
