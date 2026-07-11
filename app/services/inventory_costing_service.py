from dataclasses import dataclass
from sqlite3 import Connection

EPSILON = 0.0000001


@dataclass(frozen=True)
class CostAllocation:
    source_move_id: int
    lot_id: int | None
    quantity: float
    unit_cost: float


class InventoryCostingService:
    """Posts stock issues against the oldest available inbound cost layers."""

    def available_quantity(
        self,
        connection: Connection,
        product_id: int,
        warehouse_id: int,
    ) -> float:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS quantity
            FROM inventory_moves
            WHERE product_id = ? AND warehouse_id = ?
            """,
            (product_id, warehouse_id),
        ).fetchone()
        return float(row["quantity"] if row is not None else 0)

    def allocate_fifo(
        self,
        connection: Connection,
        product_id: int,
        warehouse_id: int,
        quantity: float,
    ) -> list[CostAllocation]:
        if quantity <= 0:
            raise ValueError("كمية الصرف يجب أن تكون أكبر من صفر")

        available = self.available_quantity(connection, product_id, warehouse_id)
        if available + EPSILON < quantity:
            raise ValueError(f"الرصيد غير كافي. المتاح {available:g} والمطلوب {quantity:g}")

        rows = connection.execute(
            """
            SELECT source.id AS source_move_id, source.lot_id, source.unit_cost,
                   source.quantity_in - COALESCE(SUM(a.quantity), 0) AS remaining
            FROM inventory_moves source
            LEFT JOIN inventory_cost_allocations a ON a.source_move_id = source.id
            WHERE source.product_id = ?
              AND source.warehouse_id = ?
              AND source.quantity_in > 0
            GROUP BY source.id, source.lot_id, source.unit_cost,
                     source.quantity_in, source.move_date
            HAVING remaining > ?
            ORDER BY source.move_date, source.id
            """,
            (product_id, warehouse_id, EPSILON),
        ).fetchall()

        remaining_to_allocate = quantity
        allocations: list[CostAllocation] = []
        for row in rows:
            if remaining_to_allocate <= EPSILON:
                break
            allocated_quantity = min(remaining_to_allocate, float(row["remaining"]))
            allocations.append(
                CostAllocation(
                    source_move_id=int(row["source_move_id"]),
                    lot_id=int(row["lot_id"]) if row["lot_id"] is not None else None,
                    quantity=allocated_quantity,
                    unit_cost=float(row["unit_cost"]),
                )
            )
            remaining_to_allocate -= allocated_quantity

        if remaining_to_allocate > EPSILON:
            raise ValueError(
                "الرصيد موجود لكن طبقات التكلفة غير مكتملة. راجع ترحيل الرصيد الافتتاحي."
            )
        return allocations

    def post_issue(
        self,
        connection: Connection,
        *,
        product_id: int,
        warehouse_id: int,
        quantity: float,
        reference_type: str,
        reference_id: int | None = None,
        partner_id: int | None = None,
        notes: str = "",
    ) -> list[int]:
        allocations = self.allocate_fifo(
            connection,
            product_id,
            warehouse_id,
            quantity,
        )
        move_ids: list[int] = []
        for allocation in allocations:
            cursor = connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                    unit_cost, reference_type, reference_id, partner_id, notes
                )
                VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    warehouse_id,
                    allocation.lot_id,
                    allocation.quantity,
                    allocation.unit_cost,
                    reference_type,
                    reference_id,
                    partner_id,
                    notes,
                ),
            )
            outbound_move_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO inventory_cost_allocations(
                    outbound_move_id, source_move_id, quantity, unit_cost
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    outbound_move_id,
                    allocation.source_move_id,
                    allocation.quantity,
                    allocation.unit_cost,
                ),
            )
            move_ids.append(outbound_move_id)
        return move_ids
