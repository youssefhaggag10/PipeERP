from app.ui.products_page import PRODUCT_TYPES, ProductsPage


class StrictProductsPage(ProductsPage):
    """Disable the standard-weight editor unless the product is a finished good."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type_input.currentIndexChanged.connect(self._sync_standard_weight_state)
        self._sync_standard_weight_state()

    def _sync_standard_weight_state(self) -> None:
        is_finished_good = PRODUCT_TYPES.get(self.type_input.currentText()) == "finished_good"
        self.standard_weight_input.setEnabled(is_finished_good)
        if not is_finished_good:
            self.standard_weight_input.setText("0")
        self.standard_weight_input.setToolTip(
            "وزن القطعة القياسي للمنتج النهائي؛ يستخدم لحساب خلطات التصنيع"
            if is_finished_good
            else "الوزن القياسي متاح للمنتج النهائي فقط"
        )

    def save_product(self) -> None:
        self._sync_standard_weight_state()
        super().save_product()

    def load_selected_product(self) -> None:
        super().load_selected_product()
        self._sync_standard_weight_state()

    def clear_editor(self) -> None:
        super().clear_editor()
        self._sync_standard_weight_state()


__all__ = ["StrictProductsPage"]
