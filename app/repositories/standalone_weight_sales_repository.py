from __future__ import annotations

from app.repositories.weight_invoice_repository import WeightInvoiceRepository


class StandaloneWeightSalesRepository(WeightInvoiceRepository):
    """Compatibility name for the independent weight-invoice workflow."""


__all__ = ["StandaloneWeightSalesRepository"]
