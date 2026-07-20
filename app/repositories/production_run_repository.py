from __future__ import annotations

from app.repositories.base_material_scrap_cost_repository import (
    BaseMaterialScrapCostRepository,
)

EPSILON = 0.0000001


class ProductionRunRepository(BaseMaterialScrapCostRepository):
    """Manufacturing orders executed as independent physical operating mixes.

    The base recipe remains a reusable master. Each manufacturing run stores a
    material snapshot, issues only the material used by that run, and records the
    actual pipe count and actual output weight before another mix can be created.
    The centralized database migrations own the run and weight-layer schema.
    """

    def start_order(self, order_id: int) -> None:
        """Open an order without issuing all planned mixes in advance."""
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT id, status FROM manufacturing_orders WHERE id = ?",
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            if str(order["status"]) == "completed":
                raise ValueError("أمر التصنيع مكتمل بالفعل")
            if str(order["status"]) == "cancelled":
                raise ValueError("لا يمكن بدء أمر تصنيع ملغي")
            if str(order["status"]) == "draft":
                connection.execute(
                    """
                    UPDATE manufacturing_orders
                    SET status = 'in_progress', started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        actual_batches = 0, material_cost = 0, finished_cost = 0,
                        weight_variance = 0, returned_scrap_quantity = 0
                    WHERE id = ?
                    """,
                    (int(order_id),),
                )
        self.ensure_current_run(int(order_id))

    def ensure_current_run(self, order_id: int) -> int:
        existing = self.database.fetch_one(
            """
            SELECT id FROM manufacturing_runs
            WHERE manufacturing_order_id = ? AND status IN ('draft', 'in_progress')
            ORDER BY run_number DESC LIMIT 1
            """,
            (int(order_id),),
        )
        if existing is not None:
            return int(existing["id"])
        count_row = self.database.fetch_one(
            "SELECT COUNT(*) AS n FROM manufacturing_runs WHERE manufacturing_order_id = ?",
            (int(order_id),),
        )
        run_count = int(count_row["n"] or 0) if count_row is not None else 0
        reason = "الخلطة الأولى" if run_count == 0 else "خلطة تشغيل إضافية من التركيبة الأصلية"
        return self._create_run_from_order(int(order_id), change_reason=reason)

    def _create_run_from_order(self, order_id: int, *, change_reason: str = "") -> int:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT id, status FROM manufacturing_orders WHERE id = ?",
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            if str(order["status"]) not in {"draft", "in_progress"}:
                raise ValueError("يمكن إنشاء خلطة تشغيل لأمر مسودة أو جارٍ فقط")
            run_number = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(run_number), 0) + 1 AS n
                    FROM manufacturing_runs WHERE manufacturing_order_id = ?
                    """,
                    (int(order_id),),
                ).fetchone()["n"]
            )
            cursor = connection.execute(
                """
                INSERT INTO manufacturing_runs(
                    manufacturing_order_id, run_number, change_reason
                ) VALUES (?, ?, ?)
                """,
                (int(order_id), run_number, change_reason.strip()),
            )
            run_id = int(cursor.lastrowid)
            materials = connection.execute(
                """
                SELECT product_id, component_kind, quantity_per_batch
                FROM manufacturing_order_materials
                WHERE manufacturing_order_id = ?
                ORDER BY id
                """,
                (int(order_id),),
            ).fetchall()
            if not materials:
                raise ValueError("أمر التصنيع لا يحتوي على خامات")
            connection.executemany(
                """
                INSERT INTO manufacturing_run_materials(
                    manufacturing_run_id, product_id, component_kind,
                    quantity_per_batch, display_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        int(row["product_id"]),
                        str(row["component_kind"]),
                        float(row["quantity_per_batch"]),
                        index * 10,
                    )
                    for index, row in enumerate(materials, start=1)
                ],
            )
            outputs = connection.execute(
                """
                SELECT product_id, standard_weight_kg
                FROM manufacturing_order_outputs
                WHERE manufacturing_order_id = ? ORDER BY id
                """,
                (int(order_id),),
            ).fetchall()
            connection.executemany(
                """
                INSERT INTO manufacturing_run_outputs(
                    manufacturing_run_id, product_id, standard_weight_kg
                ) VALUES (?, ?, ?)
                """,
                [
                    (run_id, int(row["product_id"]), float(row["standard_weight_kg"] or 0))
                    for row in outputs
                ],
            )
            self._event(connection, run_id, "created", change_reason or "إنشاء خلطة التشغيل")
            return run_id

    def clone_run_without_material(
        self,
        order_id: int,
        source_run_id: int,
        removed_product_id: int,
        reason: str,
    ) -> int:
        reason = reason.strip()
        if not reason:
            raise ValueError("اكتب سبب حذف الخامة")
        with self.database.session(immediate=True) as connection:
            source = connection.execute(
                """
                SELECT * FROM manufacturing_runs
                WHERE id = ? AND manufacturing_order_id = ?
                """,
                (int(source_run_id), int(order_id)),
            ).fetchone()
            if source is None:
                raise ValueError("خلطة التشغيل غير موجودة")
            material = connection.execute(
                """
                SELECT p.name FROM manufacturing_run_materials rm
                JOIN products p ON p.id = rm.product_id
                WHERE rm.manufacturing_run_id = ? AND rm.product_id = ?
                """,
                (int(source_run_id), int(removed_product_id)),
            ).fetchone()
            if material is None:
                raise ValueError("الخامة المختارة غير موجودة في الخلطة")
            if str(source["status"]) == "in_progress":
                raise ValueError(
                    "سجل إنتاج الخلطة الحالية وأغلقها أولًا قبل إنشاء خلطة معدلة، "
                    "حتى لا تضيع تكلفة الخامات المصروفة والإنتاج السابق"
                )
            if str(source["status"]) == "draft":
                connection.execute(
                    """
                    UPDATE manufacturing_runs
                    SET status = 'stopped', completed_at = CURRENT_TIMESTAMP,
                        change_reason = CASE WHEN TRIM(COALESCE(change_reason, '')) = ''
                            THEN ? ELSE change_reason || ' | ' || ? END
                    WHERE id = ?
                    """,
                    (reason, reason, int(source_run_id)),
                )
                self._event(connection, int(source_run_id), "stopped", reason)

            run_number = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(run_number), 0) + 1 AS n
                    FROM manufacturing_runs WHERE manufacturing_order_id = ?
                    """,
                    (int(order_id),),
                ).fetchone()["n"]
            )
            cursor = connection.execute(
                """
                INSERT INTO manufacturing_runs(
                    manufacturing_order_id, run_number, change_reason
                ) VALUES (?, ?, ?)
                """,
                (
                    int(order_id),
                    run_number,
                    f"حذف خامة {material['name']}: {reason}",
                ),
            )
            new_run_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO manufacturing_run_materials(
                    manufacturing_run_id, product_id, component_kind,
                    quantity_per_batch, display_order
                )
                SELECT ?, product_id, component_kind, quantity_per_batch, display_order
                FROM manufacturing_run_materials
                WHERE manufacturing_run_id = ? AND product_id <> ?
                """,
                (new_run_id, int(source_run_id), int(removed_product_id)),
            )
            connection.execute(
                """
                INSERT INTO manufacturing_run_outputs(
                    manufacturing_run_id, product_id, standard_weight_kg
                )
                SELECT ?, product_id, standard_weight_kg
                FROM manufacturing_run_outputs WHERE manufacturing_run_id = ?
                """,
                (new_run_id, int(source_run_id)),
            )
            self._event(
                connection,
                new_run_id,
                "created_from_previous",
                f"من الخلطة {source['run_number']} بدون {material['name']} — {reason}",
            )
            return new_run_id

    def issue_run(self, run_id: int, batches: int = 1) -> dict:
        batches = int(batches)
        if batches <= 0:
            raise ValueError("عدد الخلطات المصروفة يجب أن يكون أكبر من صفر")
        with self.database.session(immediate=True) as connection:
            run = connection.execute(
                """
                SELECT r.*, o.warehouse_id, o.order_number, o.status AS order_status
                FROM manufacturing_runs r
                JOIN manufacturing_orders o ON o.id = r.manufacturing_order_id
                WHERE r.id = ?
                """,
                (int(run_id),),
            ).fetchone()
            if run is None:
                raise ValueError("خلطة التشغيل غير موجودة")
            if str(run["order_status"]) != "in_progress":
                raise ValueError("أمر التصنيع يجب أن يكون جاريًا")
            if str(run["status"]) not in {"draft", "in_progress"}:
                raise ValueError("لا يمكن الصرف على خلطة مغلقة")

            materials = connection.execute(
                """
                SELECT rm.*, p.code, p.name
                FROM manufacturing_run_materials rm
                JOIN products p ON p.id = rm.product_id
                WHERE rm.manufacturing_run_id = ?
                ORDER BY rm.display_order, rm.id
                """,
                (int(run_id),),
            ).fetchall()
            if not materials:
                raise ValueError("خلطة التشغيل لا تحتوي على خامات")

            requirements = []
            for material in materials:
                required = float(material["quantity_per_batch"]) * batches
                available = self._available_quantity(
                    connection,
                    int(material["product_id"]),
                    int(run["warehouse_id"]),
                )
                if str(material["component_kind"]) != "scrap" and available + EPSILON < required:
                    raise ValueError(
                        f"رصيد {material['name']} غير كافٍ. المطلوب {required:,.2f} والمتاح {available:,.2f}"
                    )
                actual = (
                    min(required, available)
                    if str(material["component_kind"]) == "scrap"
                    else required
                )
                requirements.append((material, actual))

            input_weight = 0.0
            total_cost = 0.0
            for material, quantity in requirements:
                if quantity <= EPSILON:
                    continue
                move_id, unit_cost, line_cost = self._issue_fifo(
                    connection,
                    product_id=int(material["product_id"]),
                    warehouse_id=int(run["warehouse_id"]),
                    quantity=quantity,
                    reference_id=int(run_id),
                    notes=f"صرف خلطة تشغيل {run['order_number']}/{run['run_number']}",
                )
                connection.execute(
                    """
                    UPDATE manufacturing_run_materials
                    SET actual_quantity = actual_quantity + ?,
                        total_cost = total_cost + ?,
                        unit_cost = CASE
                            WHEN actual_quantity + ? > 0
                            THEN (total_cost + ?) / (actual_quantity + ?)
                            ELSE 0 END
                    WHERE id = ?
                    """,
                    (
                        quantity,
                        line_cost,
                        quantity,
                        line_cost,
                        quantity,
                        int(material["id"]),
                    ),
                )
                input_weight += quantity
                total_cost += line_cost
                self._event(
                    connection,
                    int(run_id),
                    "material_issue",
                    f"{material['name']}: {quantity:,.3f} كجم بتكلفة {line_cost:,.2f} — حركة {move_id}",
                )

            connection.execute(
                """
                UPDATE manufacturing_runs
                SET status = 'in_progress', issued_batches = issued_batches + ?,
                    actual_input_weight = actual_input_weight + ?,
                    material_cost = material_cost + ?,
                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (batches, input_weight, total_cost, int(run_id)),
            )
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET actual_batches = actual_batches + ?,
                    material_cost = material_cost + ?
                WHERE id = ?
                """,
                (batches, total_cost, int(run["manufacturing_order_id"])),
            )
            return {
                "run_id": int(run_id),
                "batches": batches,
                "input_weight": input_weight,
                "material_cost": total_cost,
            }

    def complete_run(
        self,
        run_id: int,
        *,
        outputs: dict[int, dict[str, float]],
        scrap_weight: float = 0,
        notes: str = "",
    ) -> dict:
        scrap_weight = float(scrap_weight or 0)
        if scrap_weight < 0:
            raise ValueError("وزن الكسر لا يمكن أن يكون سالبًا")
        with self.database.session(immediate=True) as connection:
            run = connection.execute(
                """
                SELECT r.*, o.warehouse_id, o.order_number, o.recipe_id,
                       mr.scrap_product_id
                FROM manufacturing_runs r
                JOIN manufacturing_orders o ON o.id = r.manufacturing_order_id
                JOIN manufacturing_recipes mr ON mr.id = o.recipe_id
                WHERE r.id = ?
                """,
                (int(run_id),),
            ).fetchone()
            if run is None:
                raise ValueError("خلطة التشغيل غير موجودة")
            if str(run["status"]) != "in_progress":
                raise ValueError("يجب صرف الخلطة أولًا قبل تسجيل الإنتاج")
            if float(run["actual_input_weight"]) <= EPSILON:
                raise ValueError("لا توجد خامات مصروفة لهذه الخلطة")

            output_rows = connection.execute(
                """
                SELECT ro.*, p.code, p.name
                FROM manufacturing_run_outputs ro
                JOIN products p ON p.id = ro.product_id
                WHERE ro.manufacturing_run_id = ? ORDER BY ro.id
                """,
                (int(run_id),),
            ).fetchall()
            normalized: list[tuple] = []
            total_good_weight = 0.0
            total_good_quantity = 0.0
            for row in output_rows:
                value = outputs.get(int(row["product_id"]), {})
                quantity = float(value.get("quantity", 0) or 0)
                actual_weight = float(value.get("actual_weight_kg", 0) or 0)
                if quantity < 0 or actual_weight < 0:
                    raise ValueError("الكمية والوزن الفعلي لا يمكن أن يكونا سالبين")
                if quantity > EPSILON and actual_weight <= EPSILON:
                    actual_weight = quantity * float(row["standard_weight_kg"] or 0)
                if quantity <= EPSILON and actual_weight > EPSILON:
                    raise ValueError(f"أدخل عدد المواسير للصنف {row['name']}")
                normalized.append((row, quantity, actual_weight))
                total_good_quantity += quantity
                total_good_weight += actual_weight

            if total_good_quantity <= EPSILON or total_good_weight <= EPSILON:
                raise ValueError("أدخل إنتاجًا سليمًا ووزنه الفعلي")
            if total_good_weight + scrap_weight - float(run["actual_input_weight"]) > EPSILON:
                raise ValueError("وزن الإنتاج والكسر لا يمكن أن يتجاوز وزن الخامات المصروفة")

            material_cost = float(run["material_cost"])
            input_weight = float(run["actual_input_weight"])
            input_unit_cost = material_cost / input_weight
            scrap_value = scrap_weight * input_unit_cost
            finished_cost = max(0.0, material_cost - scrap_value)
            cost_per_good_kg = finished_cost / total_good_weight

            for row, quantity, actual_weight in normalized:
                if quantity <= EPSILON:
                    continue
                line_cost = actual_weight * cost_per_good_kg
                unit_cost = line_cost / quantity
                connection.execute(
                    """
                    UPDATE manufacturing_run_outputs
                    SET actual_quantity = ?, actual_weight_kg = ?, unit_cost = ?
                    WHERE id = ?
                    """,
                    (quantity, actual_weight, unit_cost, int(row["id"])),
                )
                lot_number = (
                    f"{run['order_number']}-RUN{int(run['run_number']):02d}-"
                    f"FG-{int(row['product_id'])}"
                )
                lot_id = self._ensure_lot(
                    connection,
                    int(row["product_id"]),
                    lot_number,
                    unit_cost,
                )
                cursor = connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing_run', ?, ?)
                    """,
                    (
                        int(row["product_id"]),
                        int(run["warehouse_id"]),
                        lot_id,
                        quantity,
                        unit_cost,
                        int(run_id),
                        f"إنتاج خلطة تشغيل {run['order_number']}/{run['run_number']} — وزن فعلي {actual_weight:,.3f} كجم",
                    ),
                )
                source_move_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO finished_good_weight_layers(
                        product_id, warehouse_id, source_move_id, lot_id,
                        quantity_in, weight_in_kg, unit_cost_per_kg
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(row["product_id"]),
                        int(run["warehouse_id"]),
                        source_move_id,
                        lot_id,
                        quantity,
                        actual_weight,
                        cost_per_good_kg,
                    ),
                )
                connection.execute(
                    """
                    UPDATE manufacturing_order_outputs
                    SET actual_quantity = COALESCE(actual_quantity, 0) + ?,
                        unit_cost = CASE
                            WHEN COALESCE(actual_quantity, 0) + ? > 0
                            THEN (
                                COALESCE(actual_quantity, 0) * COALESCE(unit_cost, 0)
                                + ? * ?
                            ) / (COALESCE(actual_quantity, 0) + ?)
                            ELSE ? END
                    WHERE manufacturing_order_id = ? AND product_id = ?
                    """,
                    (
                        quantity,
                        quantity,
                        quantity,
                        unit_cost,
                        quantity,
                        unit_cost,
                        int(run["manufacturing_order_id"]),
                        int(row["product_id"]),
                    ),
                )

            scrap_product_id = run["scrap_product_id"]
            if scrap_weight > EPSILON and scrap_product_id is not None:
                scrap_lot = f"{run['order_number']}-RUN{int(run['run_number']):02d}-SCRAP"
                lot_id = self._ensure_lot(
                    connection,
                    int(scrap_product_id),
                    scrap_lot,
                    input_unit_cost,
                )
                connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing_run_scrap', ?, ?)
                    """,
                    (
                        int(scrap_product_id),
                        int(run["warehouse_id"]),
                        lot_id,
                        scrap_weight,
                        input_unit_cost,
                        int(run_id),
                        f"كسر خلطة تشغيل {run['order_number']}/{run['run_number']}",
                    ),
                )

            variance = input_weight - total_good_weight - scrap_weight
            connection.execute(
                """
                UPDATE manufacturing_runs
                SET status = 'completed', good_output_weight = ?, scrap_weight = ?,
                    finished_cost = ?, notes = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (total_good_weight, scrap_weight, finished_cost, notes.strip(), int(run_id)),
            )
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET returned_scrap_quantity = returned_scrap_quantity + ?,
                    finished_cost = finished_cost + ?,
                    weight_variance = weight_variance + ?
                WHERE id = ?
                """,
                (
                    scrap_weight,
                    finished_cost,
                    variance,
                    int(run["manufacturing_order_id"]),
                ),
            )
            self._event(
                connection,
                int(run_id),
                "completed",
                f"إنتاج سليم {total_good_weight:,.3f} كجم — كسر {scrap_weight:,.3f} كجم — فرق {variance:,.3f} كجم",
            )
            return {
                "run_id": int(run_id),
                "good_output_weight": total_good_weight,
                "scrap_weight": scrap_weight,
                "finished_cost": finished_cost,
                "weight_variance": variance,
                "cost_per_good_kg": cost_per_good_kg,
            }

    def close_order_from_runs(self, order_id: int) -> dict:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT id, status FROM manufacturing_orders WHERE id = ?",
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            active = int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS n FROM manufacturing_runs
                    WHERE manufacturing_order_id = ? AND status IN ('draft', 'in_progress')
                    """,
                    (int(order_id),),
                ).fetchone()["n"]
            )
            if active:
                raise ValueError("أغلق أو ألغِ كل خلطات التشغيل المفتوحة أولًا")
            summary = connection.execute(
                """
                SELECT COUNT(*) AS run_count,
                       COALESCE(SUM(material_cost), 0) AS material_cost,
                       COALESCE(SUM(finished_cost), 0) AS finished_cost,
                       COALESCE(SUM(good_output_weight), 0) AS good_weight,
                       COALESCE(SUM(scrap_weight), 0) AS scrap_weight,
                       COALESCE(SUM(actual_input_weight-good_output_weight-scrap_weight), 0) AS variance
                FROM manufacturing_runs
                WHERE manufacturing_order_id = ? AND status = 'completed'
                """,
                (int(order_id),),
            ).fetchone()
            if int(summary["run_count"] or 0) == 0:
                raise ValueError("لا توجد خلطات تشغيل مكتملة")
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET status = 'completed', material_cost = ?, finished_cost = ?,
                    returned_scrap_quantity = ?, weight_variance = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    float(summary["material_cost"]),
                    float(summary["finished_cost"]),
                    float(summary["scrap_weight"]),
                    float(summary["variance"]),
                    int(order_id),
                ),
            )
            return dict(summary)

    def list_runs(self, order_id: int) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM manufacturing_run_materials m
                    WHERE m.manufacturing_run_id = r.id) AS material_count,
                   (SELECT COALESCE(SUM(actual_quantity), 0)
                    FROM manufacturing_run_outputs o
                    WHERE o.manufacturing_run_id = r.id) AS output_quantity
            FROM manufacturing_runs r
            WHERE r.manufacturing_order_id = ?
            ORDER BY r.run_number
            """,
            (int(order_id),),
        )
        return [dict(row) for row in rows]

    def get_run(self, run_id: int) -> dict:
        row = self.database.fetch_one(
            """
            SELECT r.*, o.order_number, o.warehouse_id
            FROM manufacturing_runs r
            JOIN manufacturing_orders o ON o.id = r.manufacturing_order_id
            WHERE r.id = ?
            """,
            (int(run_id),),
        )
        if row is None:
            raise ValueError("خلطة التشغيل غير موجودة")
        result = dict(row)
        result["materials"] = [
            dict(item)
            for item in self.database.fetch_all(
                """
                SELECT rm.*, p.code, p.name
                FROM manufacturing_run_materials rm
                JOIN products p ON p.id = rm.product_id
                WHERE rm.manufacturing_run_id = ? ORDER BY rm.display_order, rm.id
                """,
                (int(run_id),),
            )
        ]
        result["outputs"] = [
            dict(item)
            for item in self.database.fetch_all(
                """
                SELECT ro.*, p.code, p.name
                FROM manufacturing_run_outputs ro
                JOIN products p ON p.id = ro.product_id
                WHERE ro.manufacturing_run_id = ? ORDER BY ro.id
                """,
                (int(run_id),),
            )
        ]
        return result

    @staticmethod
    def _available_quantity(connection, product_id: int, warehouse_id: int) -> float:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS balance
            FROM inventory_moves WHERE product_id = ? AND warehouse_id = ?
            """,
            (int(product_id), int(warehouse_id)),
        ).fetchone()
        return float(row["balance"] or 0)

    @staticmethod
    def _issue_fifo(
        connection,
        *,
        product_id: int,
        warehouse_id: int,
        quantity: float,
        reference_id: int,
        notes: str,
    ) -> tuple[int, float, float]:
        remaining = float(quantity)
        sources = connection.execute(
            """
            SELECT source.id, source.unit_cost,
                   source.quantity_in - COALESCE(SUM(a.quantity), 0) AS remaining
            FROM inventory_moves source
            LEFT JOIN inventory_cost_allocations a ON a.source_move_id = source.id
            WHERE source.product_id = ? AND source.warehouse_id = ?
              AND source.quantity_in > 0
            GROUP BY source.id, source.unit_cost, source.quantity_in, source.move_date
            HAVING remaining > 0.0000001
            ORDER BY source.move_date, source.id
            """,
            (int(product_id), int(warehouse_id)),
        ).fetchall()
        available = sum(float(row["remaining"]) for row in sources)
        if available + EPSILON < remaining:
            raise ValueError("الرصيد غير كافٍ لإتمام الصرف")

        allocations: list[tuple[int, float, float]] = []
        total_cost = 0.0
        for source in sources:
            if remaining <= EPSILON:
                break
            allocated = min(remaining, float(source["remaining"]))
            unit_cost = float(source["unit_cost"] or 0)
            allocations.append((int(source["id"]), allocated, unit_cost))
            total_cost += allocated * unit_cost
            remaining -= allocated
        average_cost = total_cost / float(quantity)
        cursor = connection.execute(
            """
            INSERT INTO inventory_moves(
                product_id, warehouse_id, quantity_in, quantity_out, unit_cost,
                reference_type, reference_id, notes
            ) VALUES (?, ?, 0, ?, ?, 'manufacturing_run', ?, ?)
            """,
            (
                int(product_id),
                int(warehouse_id),
                float(quantity),
                average_cost,
                int(reference_id),
                notes,
            ),
        )
        outbound_move_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO inventory_cost_allocations(
                outbound_move_id, source_move_id, quantity, unit_cost
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (outbound_move_id, source_id, allocated, unit_cost)
                for source_id, allocated, unit_cost in allocations
            ],
        )
        return outbound_move_id, average_cost, total_cost

    @staticmethod
    def _ensure_lot(connection, product_id: int, lot_number: str, unit_cost: float) -> int:
        connection.execute(
            """
            INSERT OR IGNORE INTO lots(product_id, lot_number, unit_cost)
            VALUES (?, ?, ?)
            """,
            (int(product_id), lot_number, float(unit_cost)),
        )
        connection.execute(
            """
            UPDATE lots SET unit_cost = ? WHERE product_id = ? AND lot_number = ?
            """,
            (float(unit_cost), int(product_id), lot_number),
        )
        row = connection.execute(
            "SELECT id FROM lots WHERE product_id = ? AND lot_number = ?",
            (int(product_id), lot_number),
        ).fetchone()
        return int(row["id"])

    @staticmethod
    def _event(connection, run_id: int, event_type: str, details: str) -> None:
        connection.execute(
            """
            INSERT INTO manufacturing_run_events(
                manufacturing_run_id, event_type, details
            ) VALUES (?, ?, ?)
            """,
            (int(run_id), event_type, details.strip()),
        )


__all__ = ["ProductionRunRepository"]
