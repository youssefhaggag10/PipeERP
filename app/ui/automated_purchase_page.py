from datetime import datetime
from uuid import uuid4

from app.ui.accounting_order_pages import PurchaseAccountingPage


class AutomatedPurchaseAccountingPage(PurchaseAccountingPage):
    """Purchase page that generates a lot number when the user leaves it blank."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.lot_input.setPlaceholderText("سيُنشئ النظام رقم الدفعة تلقائيًا")
        self.lot_input.setToolTip(
            "اترك الحقل فارغًا ليُنشئ النظام رقم Lot فريدًا تلقائيًا، أو أدخل رقم المورد عند الحاجة."
        )

    def add_or_update_line(self) -> None:
        if not self.lot_input.text().strip():
            product_id = self.product_input.currentData()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            product_token = str(product_id or "ITEM")
            generated = f"PUR-{product_token}-{stamp}-{uuid4().hex[:6].upper()}"
            self.lot_input.setText(generated)
        super().add_or_update_line()


__all__ = ["AutomatedPurchaseAccountingPage"]
