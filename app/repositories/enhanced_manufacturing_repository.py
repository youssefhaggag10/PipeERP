from app.repositories.manufacturing_repository import ManufacturingRepository


class EnhancedManufacturingRepository(ManufacturingRepository):
    """Extra manufacturing actions with inventory-safe cancellation."""

    @staticmethod
    def _normalize_recipe_data(
        *,
        code: str,
        name: str,
        output_product_ids: list[int],
        components: list[dict],
        suggested_scrap_per_batch: float,
    ) -> tuple[str, str, list[int], list[tuple[int, float]], float]:
        normalized_code = code.strip().upper()
        normalized_name = name.strip()
        outputs = list(dict.fromkeys(int(value) for value in output_product_ids))
        scrap_quantity = float(suggested_scrap_per_batch or 0)
        if not normalized_code or not normalized_name:
            raise ValueError("كود واسم الخلطة مطلوبان")
        if not outputs:
            raise ValueError("اربط الخلطة بمنتج نهائي واحد على الأقل")
        if not components:
            raise ValueError("أضف خامة واحدة على الأقل للخلطة")
        if scrap_quantity < 0:
            raise ValueError("كمية الكسر المقترحة لا يمكن أن تكون سالبة")

        normalized_components: list[tuple[int, float]] = []
        seen_products: set[int] = set()
        for index, component in enumerate(components, start=1):
            product_id = int(component["product_id"])
            quantity = float(component["quantity_per_batch"])
            if quantity <= 0:
                raise ValueError(f"كمية خامة الخلطة رقم {index} يجب أن تكون أكبر من صفر")
            if product_id in seen_products:
                raise ValueError("لا يمكن تكرار نفس الخامة داخل الخلطة")
            seen_products.add(product_id)
            normalized_components.append((product_id, quantity))
        return (
            normalized_code,
            normalized_name,
            outputs,
            normalized_components,
            scrap_quantity,
        )

    def update_recipe(
        self,
        recipe_id: int,
        *,
        code: str,
        name: str,
        output_product_ids: list[int],
        components: list[dict],
        suggested_scrap_per_batch: float = 0,
        notes: str = "",
    ) -> None:
        (
            code,
            name,
            output_product_ids,
            normalized_components,
            suggested_scrap_per_batch,
        ) = self._normalize_recipe_data(
            code=code,
            name=name,
            output_product_ids=output_product_ids,
            components=components,
            suggested_scrap_per_batch=suggested_scrap_per_batch,
        )

        with self.database.session(immediate=True) as connection:
            recipe = connection.execute(
                "SELECT * FROM manufacturing_recipes WHERE id = ? AND is_active = 1",
                (recipe_id,),
            ).fetchone()
            if recipe is None:
                raise ValueError("الخلطة غير موجودة")

            duplicate = connection.execute(
                """
                SELECT id FROM manufacturing_recipes
                WHERE id <> ? AND is_active = 1 AND (code = ? OR name = ?)
                """,
                (recipe_id, code, name),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("كود أو اسم الخلطة مستخدم بالفعل")

            placeholders = ",".join("?" for _ in output_product_ids)
            outputs = connection.execute(
                f"""
                SELECT id, standard_weight_kg FROM products
                WHERE id IN ({placeholders}) AND product_type = 'finished_good'
                  AND is_active = 1
                """,
                tuple(output_product_ids),
            ).fetchall()
            if len(outputs) != len(output_product_ids):
                raise ValueError("أحد المنتجات النهائية غير موجود أو غير نشط")
            if any(float(row["standard_weight_kg"]) <= 0 for row in outputs):
                raise ValueError("سجل الوزن القياسي لكل منتج نهائي قبل ربطه بالخلطة")

            linked_elsewhere = connection.execute(
                f"""
                SELECT ro.product_id
                FROM manufacturing_recipe_outputs ro
                JOIN manufacturing_recipes r ON r.id = ro.recipe_id
                WHERE ro.recipe_id <> ? AND r.is_active = 1
                  AND ro.product_id IN ({placeholders})
                LIMIT 1
                """,
                (recipe_id, *output_product_ids),
            ).fetchone()
            if linked_elsewhere is not None:
                raise ValueError("أحد المنتجات النهائية مرتبط بخلطة أخرى")

            for product_id, _ in normalized_components:
                product = connection.execute(
                    """
                    SELECT id FROM products
                    WHERE id = ? AND product_type IN ('raw_material', 'waste')
                      AND is_active = 1
                    """,
                    (product_id,),
                ).fetchone()
                if product is None:
                    raise ValueError("خامات الخلطة يجب أن تكون خامات أو كسر مصنع نشط")

            connection.execute(
                """
                UPDATE manufacturing_recipes
                SET code = ?, name = ?, notes = ?
                WHERE id = ?
                """,
                (code, name, notes.strip(), recipe_id),
            )
            connection.execute(
                "DELETE FROM manufacturing_recipe_outputs WHERE recipe_id = ?",
                (recipe_id,),
            )
            connection.execute(
                "DELETE FROM manufacturing_recipe_components WHERE recipe_id = ?",
                (recipe_id,),
            )
            connection.executemany(
                """
                INSERT INTO manufacturing_recipe_outputs(recipe_id, product_id)
                VALUES (?, ?)
                """,
                [(recipe_id, product_id) for product_id in output_product_ids],
            )
            connection.executemany(
                """
                INSERT INTO manufacturing_recipe_components(
                    recipe_id, product_id, component_kind,
                    quantity_per_batch, display_order
                ) VALUES (?, ?, 'material', ?, ?)
                """,
                [
                    (recipe_id, product_id, quantity, index)
                    for index, (product_id, quantity) in enumerate(normalized_components, start=1)
                ],
            )
            if suggested_scrap_per_batch > 0:
                connection.execute(
                    """
                    INSERT INTO manufacturing_recipe_components(
                        recipe_id, product_id, component_kind,
                        quantity_per_batch, display_order
                    ) VALUES (?, NULL, 'optional_scrap', ?, ?)
                    """,
                    (
                        recipe_id,
                        suggested_scrap_per_batch,
                        len(normalized_components) + 1,
                    ),
                )

            scrap_product_id = recipe["scrap_product_id"]
            if scrap_product_id is not None:
                desired_scrap_code = f"SCRAP-{code}"
                conflict = connection.execute(
                    "SELECT id FROM products WHERE code = ? AND id <> ?",
                    (desired_scrap_code, scrap_product_id),
                ).fetchone()
                if conflict is None:
                    connection.execute(
                        "UPDATE products SET code = ?, name = ? WHERE id = ?",
                        (desired_scrap_code, f"كسر مصنع - {name}", scrap_product_id),
                    )
                else:
                    connection.execute(
                        "UPDATE products SET name = ? WHERE id = ?",
                        (f"كسر مصنع - {name}", scrap_product_id),
                    )

    def delete_draft_order(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT status FROM manufacturing_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            if order["status"] != "draft":
                raise ValueError("يمكن حذف أمر التصنيع وهو مسودة فقط")
            connection.execute(
                "DELETE FROM manufacturing_order_materials WHERE manufacturing_order_id = ?",
                (order_id,),
            )
            connection.execute(
                "DELETE FROM manufacturing_order_outputs WHERE manufacturing_order_id = ?",
                (order_id,),
            )
            connection.execute(
                "DELETE FROM manufacturing_orders WHERE id = ?",
                (order_id,),
            )

    def cancel_order(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT * FROM manufacturing_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            status = str(order["status"])
            if status == "completed":
                raise ValueError("لا يمكن إلغاء أمر مكتمل لأنه أثّر على المخزون والتكلفة")
            if status == "cancelled":
                raise ValueError("أمر التصنيع ملغي بالفعل")
            if status == "draft":
                raise ValueError("المسودة تُحذف بدل إلغائها")

            issued_moves = connection.execute(
                """
                SELECT product_id, warehouse_id, lot_id, quantity_out, unit_cost
                FROM inventory_moves
                WHERE reference_type = 'manufacturing' AND reference_id = ?
                  AND quantity_out > 0
                """,
                (order_id,),
            ).fetchall()
            for move in issued_moves:
                connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id,
                        quantity_in, quantity_out, unit_cost,
                        reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing_cancel', ?, ?)
                    """,
                    (
                        move["product_id"],
                        move["warehouse_id"],
                        move["lot_id"],
                        move["quantity_out"],
                        move["unit_cost"],
                        order_id,
                        f"رد خامات إلغاء أمر تصنيع {order['order_number']}",
                    ),
                )

            connection.execute(
                """
                UPDATE manufacturing_order_materials
                SET actual_quantity = 0, unit_cost = 0, total_cost = 0
                WHERE manufacturing_order_id = ?
                """,
                (order_id,),
            )
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET status = 'cancelled', actual_batches = 0,
                    material_cost = 0, finished_cost = 0,
                    weight_variance = 0, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (order_id,),
            )


__all__ = ["EnhancedManufacturingRepository"]
