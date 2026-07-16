from app.repositories.product_repository import ProductRepository


class StrictProductRepository(ProductRepository):
    """Guarantee that only finished goods can keep a standard piece weight."""

    @staticmethod
    def _normalize(data: dict) -> dict:
        normalized = dict(data)
        if str(normalized.get("product_type")) != "finished_good":
            normalized["standard_weight_kg"] = 0.0
        return normalized

    def create_product(self, data: dict) -> int:
        return super().create_product(self._normalize(data))

    def update_product(self, product_id: int, data: dict) -> None:
        super().update_product(product_id, self._normalize(data))


__all__ = ["StrictProductRepository"]
