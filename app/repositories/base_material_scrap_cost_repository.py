from app.repositories.scrap_aware_manufacturing_repository import (
    ScrapAwareManufacturingRepository,
)


EPSILON = 0.0000001


class BaseMaterialScrapCostRepository(ScrapAwareManufacturingRepository):
    """Dynamic manufacturing scrap costing based on all actual input materials.

    The recipe stores a current estimated scrap cost calculated from its base raw
    materials.  Completed manufacturing orders value their produced scrap from the
    weighted average cost of every kilogram actually issued, including reused scrap.
    """

    def __init__(self, database) -> None:
        super().__init__(database)
        self._ensure_recipe_cost_schema()

    def _ensure_recipe_cost_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            columns = {
                str(row[1])
                for