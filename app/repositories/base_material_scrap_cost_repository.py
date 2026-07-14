from app.repositories.scrap_aware_manufacturing_repository import (
    ScrapAwareManufacturingRepository,
)


EPSILON = 0.0000001


class BaseMaterialScrapCostRepository(ScrapAwareManufacturingRepository):
    """Values new manufacturing scrap from base recipe materials only.

    Used scrap remains part of the manufacturing order's total material cost, but it does
    not dilute