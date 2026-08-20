import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.common.decimal import money, quantity
from app.domain.manufacturing.completion import (
    CompletionMaterial,
    CompletionOutput,
    CompletionPlan,
    MixAdjustment,
    calculate_completion_plan,
)
from app.domain.manufacturing.planning import (
    BatchPlan,
    calculate_batch_plan,
    replan_for_available_scrap,
    target,
)
from app.modules.identity.service import ClientContext, Principal, add_audit
from app.modules.inventory.models import InventoryBalance
from app.modules.inventory.schemas import IssueRequest, ReceiptRequest
from app.modules.inventory.service import post_issue, post_receipt
from app.modules.manufacturing.models import (
    ManufacturingCompletion,
    ManufacturingCompletionOutput,
    ManufacturingMaterialIssue,
    ManufacturingMixAdjustment,
    ManufacturingMixAdjustmentMaterial,
    ManufacturingOrder,
    ManufacturingOrderMaterial,
    ManufacturingOrderOutput,
    ManufacturingRecipe,
    ManufacturingRecipeComponent,
    ManufacturingRecipeOutput,
)
from app.modules.manufacturing.schemas import (
    CancelManufacturingOrderRequest,
    CompleteManufacturingOrderRequest,
    CompletionView,
    ComponentKind,
    CreateManufacturingOrderRequest,
    CreateRecipeRequest,
    ManufacturingOption,
    ManufacturingOptionsView,
    ManufacturingOrderView,
    ManufacturingStatus,
    MaterialIssueView,
    MixAdjustmentMaterialView,
    MixAdjustmentView,
    OrderMaterialView,
    OrderOutputView,
    RecipeComponentView,
    RecipeOutputView,
    RecipeView,
    ReplanView,
    TransitionRequest,
    UpdateManufacturingOrderRequest,
    UpdateRecipeRequest,
)
from app.modules.master_data.models import Product, Warehouse
from app.modules.master_data.service import allocate_document_number, normalize_code


class ManufacturingError(Exception):
    pass


class ManufacturingNotFound(ManufacturingError):
    pass


class ManufacturingConflict(ManufacturingError):
    pass


def _normalized_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("اسم الخلطة مطلوب")
    return normalized.casefold()


def _request_hash(payload: BaseModel) -> str:
    return sha256(payload.model_dump_json().encode()).hexdigest()


def _derived_key(operation_key: str, entity_id: UUID, action: str) -> str:
    return sha256(f"{operation_key}:{entity_id}:{action}".encode()).hexdigest()


def _load_products(
    db: Session, product_ids: set[UUID], *, lock: bool = False
) -> dict[UUID, Product]:
    if not product_ids:
        return {}
    statement = select(Product).where(Product.id.in_(product_ids)).order_by(Product.id)
    if lock:
        statement = statement.with_for_update()
    return {item.id: item for item in db.scalars(statement)}


def _recipe_view(db: Session, recipe: ManufacturingRecipe) -> RecipeView:
    output_rows = list(
        db.scalars(
            select(ManufacturingRecipeOutput)
            .where(ManufacturingRecipeOutput.recipe_id == recipe.id)
            .order_by(ManufacturingRecipeOutput.created_at, ManufacturingRecipeOutput.id)
        )
    )
    component_rows = list(
        db.scalars(
            select(ManufacturingRecipeComponent)
            .where(ManufacturingRecipeComponent.recipe_id == recipe.id)
            .order_by(
                ManufacturingRecipeComponent.display_order,
                ManufacturingRecipeComponent.id,
            )
        )
    )
    products = _load_products(
        db,
        {
            recipe.scrap_product_id,
            *(item.product_id for item in output_rows),
            *(item.product_id for item in component_rows),
        },
    )
    return RecipeView(
        id=recipe.id,
        code=recipe.code,
        name_ar=recipe.name_ar,
        scrap_product_id=recipe.scrap_product_id,
        scrap_product_code=products[recipe.scrap_product_id].code,
        suggested_scrap_per_batch=recipe.suggested_scrap_per_batch,
        notes=recipe.notes,
        is_active=recipe.is_active,
        version=recipe.version,
        outputs=[
            RecipeOutputView(
                id=item.id,
                product_id=item.product_id,
                product_code=products[item.product_id].code,
                product_name_ar=products[item.product_id].name_ar,
                standard_weight_kg=products[item.product_id].standard_weight_kg,
            )
            for item in output_rows
        ],
        components=[
            RecipeComponentView(
                id=item.id,
                product_id=item.product_id,
                product_code=products[item.product_id].code,
                product_name_ar=products[item.product_id].name_ar,
                quantity_per_batch=item.quantity_per_batch,
                display_order=item.display_order,
            )
            for item in component_rows
        ],
    )


def _completion_view(db: Session, completion: ManufacturingCompletion) -> CompletionView:
    adjustments = list(
        db.scalars(
            select(ManufacturingMixAdjustment)
            .where(ManufacturingMixAdjustment.completion_id == completion.id)
            .order_by(ManufacturingMixAdjustment.created_at, ManufacturingMixAdjustment.id)
        )
    )
    quantities = list(
        db.scalars(
            select(ManufacturingMixAdjustmentMaterial)
            .where(
                ManufacturingMixAdjustmentMaterial.adjustment_id.in_(
                    {item.id for item in adjustments}
                )
            )
            .order_by(
                ManufacturingMixAdjustmentMaterial.created_at,
                ManufacturingMixAdjustmentMaterial.id,
            )
        )
    ) if adjustments else []
    quantities_by_adjustment: dict[UUID, list[ManufacturingMixAdjustmentMaterial]] = {}
    for item in quantities:
        quantities_by_adjustment.setdefault(item.adjustment_id, []).append(item)
    product_ids = {
        *(item.excluded_product_id for item in adjustments),
        *(item.product_id for item in quantities),
    }
    products = _load_products(db, product_ids)
    return CompletionView(
        id=completion.id,
        actual_batches=completion.actual_batches,
        full_batches=completion.full_batches,
        modified_batches=completion.modified_batches,
        good_output_quantity=completion.good_output_quantity,
        defective_output_quantity=completion.defective_output_quantity,
        actual_output_weight_kg=completion.actual_output_weight_kg,
        scrap_weight_kg=completion.scrap_weight_kg,
        used_input_weight_kg=completion.used_input_weight_kg,
        full_mix_cost=completion.full_mix_cost,
        modified_mix_cost=completion.modified_mix_cost,
        total_material_cost=completion.total_material_cost,
        average_input_cost_per_kg=completion.average_input_cost_per_kg,
        scrap_value=completion.scrap_value,
        finished_cost=completion.finished_cost,
        cost_per_good_kg=completion.cost_per_good_kg,
        weight_variance_kg=completion.weight_variance_kg,
        notes=completion.notes,
        adjustments=[
            MixAdjustmentView(
                id=item.id,
                excluded_product_id=item.excluded_product_id,
                excluded_product_code=products[item.excluded_product_id].code,
                excluded_product_name_ar=products[item.excluded_product_id].name_ar,
                batch_count=item.batch_count,
                reason=item.reason,
                cost_amount=item.cost_amount,
                actual_material_quantities=[
                    MixAdjustmentMaterialView(
                        product_id=value.product_id,
                        product_code=products[value.product_id].code,
                        product_name_ar=products[value.product_id].name_ar,
                        actual_quantity=value.actual_quantity,
                    )
                    for value in quantities_by_adjustment.get(item.id, [])
                ],
            )
            for item in adjustments
        ],
    )


def _order_view(db: Session, order: ManufacturingOrder) -> ManufacturingOrderView:
    recipe = db.get(ManufacturingRecipe, order.recipe_id)
    warehouse = db.get(Warehouse, order.warehouse_id)
    if recipe is None or warehouse is None:
        raise ManufacturingNotFound("مرجع أمر التصنيع غير موجود")
    outputs = list(
        db.scalars(
            select(ManufacturingOrderOutput)
            .where(ManufacturingOrderOutput.manufacturing_order_id == order.id)
            .order_by(ManufacturingOrderOutput.created_at, ManufacturingOrderOutput.id)
        )
    )
    materials = list(
        db.scalars(
            select(ManufacturingOrderMaterial)
            .where(ManufacturingOrderMaterial.manufacturing_order_id == order.id)
            .order_by(ManufacturingOrderMaterial.created_at, ManufacturingOrderMaterial.id)
        )
    )
    products = _load_products(
        db,
        {*(item.product_id for item in outputs), *(item.product_id for item in materials)},
    )
    issues = (
        list(
            db.scalars(
                select(ManufacturingMaterialIssue)
                .where(
                    ManufacturingMaterialIssue.order_material_id.in_(
                        {item.id for item in materials}
                    )
                )
                .order_by(ManufacturingMaterialIssue.created_at, ManufacturingMaterialIssue.id)
            )
        )
        if materials
        else []
    )
    issues_by_material: dict[UUID, list[ManufacturingMaterialIssue]] = {}
    for item in issues:
        issues_by_material.setdefault(item.order_material_id, []).append(item)
    completion = db.scalar(
        select(ManufacturingCompletion).where(
            ManufacturingCompletion.manufacturing_order_id == order.id
        )
    )
    return ManufacturingOrderView(
        id=order.id,
        order_number=order.order_number,
        recipe_id=order.recipe_id,
        recipe_code=recipe.code,
        recipe_name_ar=recipe.name_ar,
        warehouse_id=order.warehouse_id,
        warehouse_name_ar=warehouse.name_ar,
        status=cast(ManufacturingStatus, order.status),
        order_date=order.order_date,
        planned_batches=order.planned_batches,
        issued_batches=order.issued_batches,
        actual_batches=order.actual_batches,
        target_weight_kg=order.target_weight_kg,
        planned_input_weight_kg=order.planned_input_weight_kg,
        returned_scrap_quantity=order.returned_scrap_quantity,
        material_cost=order.material_cost,
        finished_cost=order.finished_cost,
        weight_variance_kg=order.weight_variance_kg,
        notes=order.notes,
        cancellation_reason=order.cancellation_reason,
        started_at=order.started_at,
        completed_at=order.completed_at,
        cancelled_at=order.cancelled_at,
        version=order.version,
        outputs=[
            OrderOutputView(
                id=item.id,
                product_id=item.product_id,
                product_code=products[item.product_id].code,
                product_name_ar=products[item.product_id].name_ar,
                planned_quantity=item.planned_quantity,
                standard_weight_kg=item.standard_weight_kg,
                good_quantity=item.good_quantity,
                defective_quantity=item.defective_quantity,
                actual_weight_kg=item.actual_weight_kg,
                unit_cost=item.unit_cost,
                line_cost=item.line_cost,
            )
            for item in outputs
        ],
        materials=[
            OrderMaterialView(
                id=item.id,
                product_id=item.product_id,
                product_code=products[item.product_id].code,
                product_name_ar=products[item.product_id].name_ar,
                component_kind=cast(ComponentKind, item.component_kind),
                quantity_per_batch=item.quantity_per_batch,
                planned_quantity=item.planned_quantity,
                issued_quantity=item.issued_quantity,
                used_quantity=item.used_quantity,
                returned_quantity=item.returned_quantity,
                issued_cost=item.issued_cost,
                used_cost=item.used_cost,
                issues=[
                    MaterialIssueView.model_validate(issue)
                    for issue in issues_by_material.get(item.id, [])
                ],
            )
            for item in materials
        ],
        completion=_completion_view(db, completion) if completion else None,
    )


def _validate_recipe_products(
    db: Session,
    *,
    output_ids: set[UUID],
    component_ids: set[UUID],
    excluding_recipe_id: UUID | None = None,
) -> tuple[dict[UUID, Product], dict[UUID, Product]]:
    all_products = _load_products(db, output_ids | component_ids, lock=True)
    if set(all_products) != output_ids | component_ids:
        raise ManufacturingNotFound("أحد منتجات الخلطة غير موجود")
    outputs = {item_id: all_products[item_id] for item_id in output_ids}
    components = {item_id: all_products[item_id] for item_id in component_ids}
    if any(
        not item.is_active or item.product_type != "finished_good" or item.standard_weight_kg <= 0
        for item in outputs.values()
    ):
        raise ManufacturingConflict("المنتجات النهائية يجب أن تكون نشطة ولها وزن قياسي موجب")
    if any(
        not item.is_active or item.product_type not in {"raw_material", "waste"}
        for item in components.values()
    ):
        raise ManufacturingConflict("خامات الخلطة يجب أن تكون خامات أو كسر مصنع نشط")
    linked = (
        select(ManufacturingRecipeOutput.product_id)
        .join(
            ManufacturingRecipe,
            ManufacturingRecipe.id == ManufacturingRecipeOutput.recipe_id,
        )
        .where(
            ManufacturingRecipe.is_active.is_(True),
            ManufacturingRecipeOutput.product_id.in_(output_ids),
        )
    )
    if excluding_recipe_id is not None:
        linked = linked.where(ManufacturingRecipe.id != excluding_recipe_id)
    if db.scalar(linked.limit(1)) is not None:
        raise ManufacturingConflict("أحد المنتجات النهائية مرتبط بخلطة نشطة أخرى")
    return outputs, components


def _create_scrap_product(
    db: Session,
    *,
    recipe_code: str,
    recipe_name: str,
    unit_id: UUID,
) -> Product:
    scrap_code = normalize_code(f"SCRAP-{recipe_code}")
    existing = db.scalar(select(Product).where(Product.normalized_code == scrap_code))
    if existing is not None:
        if existing.product_type != "waste":
            raise ManufacturingConflict("كود كسر الخلطة مستخدم لمنتج غير صالح")
        return existing
    product = Product(
        code=scrap_code,
        normalized_code=scrap_code,
        name_ar=f"كسر مصنع - {recipe_name}",
        product_type="waste",
        unit_id=unit_id,
        category_id=None,
        min_stock=Decimal("0"),
        track_lots=True,
        standard_weight_kg=Decimal("0"),
        weight_tolerance_percent=Decimal("5"),
        is_active=True,
        version=1,
    )
    db.add(product)
    db.flush()
    return product


def create_recipe(
    db: Session,
    *,
    payload: CreateRecipeRequest,
    actor: Principal,
    client: ClientContext,
) -> RecipeView:
    code = normalize_code(payload.code)
    normalized_name = _normalized_name(payload.name_ar)
    if (
        db.scalar(
            select(ManufacturingRecipe.id).where(
                (ManufacturingRecipe.normalized_code == code)
                | (ManufacturingRecipe.normalized_name == normalized_name)
            )
        )
        is not None
    ):
        raise ManufacturingConflict("كود أو اسم الخلطة مستخدم بالفعل")
    output_ids = set(payload.output_product_ids)
    component_ids = {item.product_id for item in payload.components}
    outputs, components = _validate_recipe_products(
        db, output_ids=output_ids, component_ids=component_ids
    )
    first_component = components[payload.components[0].product_id]
    scrap = _create_scrap_product(
        db,
        recipe_code=code,
        recipe_name=payload.name_ar.strip(),
        unit_id=first_component.unit_id,
    )
    recipe = ManufacturingRecipe(
        code=code,
        normalized_code=code,
        name_ar=payload.name_ar.strip(),
        normalized_name=normalized_name,
        scrap_product_id=scrap.id,
        suggested_scrap_per_batch=quantity(payload.suggested_scrap_per_batch),
        notes=payload.notes.strip(),
        is_active=True,
        version=1,
        created_by_id=actor.user.id,
    )
    db.add(recipe)
    db.flush()
    db.add_all(
        [
            ManufacturingRecipeOutput(recipe_id=recipe.id, product_id=item_id)
            for item_id in output_ids
        ]
    )
    db.add_all(
        [
            ManufacturingRecipeComponent(
                recipe_id=recipe.id,
                product_id=item.product_id,
                quantity_per_batch=quantity(item.quantity_per_batch),
                display_order=index,
            )
            for index, item in enumerate(payload.components, start=1)
        ]
    )
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.recipe.create",
        entity_type="manufacturing_recipe",
        entity_id=str(recipe.id),
        outcome="success",
        client=client,
        after_state={"code": code, "outputs": len(outputs), "components": len(components)},
    )
    return _recipe_view(db, recipe)


def update_recipe(
    db: Session,
    *,
    recipe_id: UUID,
    payload: UpdateRecipeRequest,
    actor: Principal,
    client: ClientContext,
) -> RecipeView:
    recipe = db.scalar(
        select(ManufacturingRecipe).where(ManufacturingRecipe.id == recipe_id).with_for_update()
    )
    if recipe is None or not recipe.is_active:
        raise ManufacturingNotFound("الخلطة غير موجودة")
    if recipe.version != payload.version:
        raise ManufacturingConflict("تم تعديل الخلطة بواسطة مستخدم آخر؛ حدّث الصفحة")
    code = normalize_code(payload.code)
    normalized_name = _normalized_name(payload.name_ar)
    duplicate = db.scalar(
        select(ManufacturingRecipe.id).where(
            ManufacturingRecipe.id != recipe.id,
            (ManufacturingRecipe.normalized_code == code)
            | (ManufacturingRecipe.normalized_name == normalized_name),
        )
    )
    if duplicate is not None:
        raise ManufacturingConflict("كود أو اسم الخلطة مستخدم بالفعل")
    _validate_recipe_products(
        db,
        output_ids=set(payload.output_product_ids),
        component_ids={item.product_id for item in payload.components},
        excluding_recipe_id=recipe.id,
    )
    before = {"code": recipe.code, "version": recipe.version}
    recipe.code = code
    recipe.normalized_code = code
    recipe.name_ar = payload.name_ar.strip()
    recipe.normalized_name = normalized_name
    recipe.suggested_scrap_per_batch = quantity(payload.suggested_scrap_per_batch)
    recipe.notes = payload.notes.strip()
    recipe.version += 1
    db.execute(
        delete(ManufacturingRecipeOutput).where(ManufacturingRecipeOutput.recipe_id == recipe.id)
    )
    db.execute(
        delete(ManufacturingRecipeComponent).where(
            ManufacturingRecipeComponent.recipe_id == recipe.id
        )
    )
    db.add_all(
        [
            ManufacturingRecipeOutput(recipe_id=recipe.id, product_id=item_id)
            for item_id in payload.output_product_ids
        ]
    )
    db.add_all(
        [
            ManufacturingRecipeComponent(
                recipe_id=recipe.id,
                product_id=item.product_id,
                quantity_per_batch=quantity(item.quantity_per_batch),
                display_order=index,
            )
            for index, item in enumerate(payload.components, start=1)
        ]
    )
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.recipe.update",
        entity_type="manufacturing_recipe",
        entity_id=str(recipe.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={"code": code, "version": recipe.version},
    )
    return _recipe_view(db, recipe)


def list_recipes(db: Session, *, include_inactive: bool = False) -> list[RecipeView]:
    statement = select(ManufacturingRecipe).order_by(
        ManufacturingRecipe.created_at.desc(), ManufacturingRecipe.id.desc()
    )
    if not include_inactive:
        statement = statement.where(ManufacturingRecipe.is_active.is_(True))
    return [_recipe_view(db, item) for item in db.scalars(statement)]


def get_recipe(db: Session, recipe_id: UUID) -> RecipeView:
    recipe = db.get(ManufacturingRecipe, recipe_id)
    if recipe is None:
        raise ManufacturingNotFound("الخلطة غير موجودة")
    return _recipe_view(db, recipe)


def _order_snapshot(
    db: Session,
    *,
    recipe: ManufacturingRecipe,
    payload: CreateManufacturingOrderRequest | UpdateManufacturingOrderRequest,
) -> tuple[list[tuple[UUID, Decimal, Decimal]], list[tuple[UUID, str, Decimal]], BatchPlan]:
    recipe_outputs = list(
        db.scalars(
            select(ManufacturingRecipeOutput).where(
                ManufacturingRecipeOutput.recipe_id == recipe.id
            )
        )
    )
    recipe_components = list(
        db.scalars(
            select(ManufacturingRecipeComponent)
            .where(ManufacturingRecipeComponent.recipe_id == recipe.id)
            .order_by(ManufacturingRecipeComponent.display_order)
        )
    )
    allowed_output_ids = {item.product_id for item in recipe_outputs}
    requested_output_ids = {item.product_id for item in payload.outputs}
    if not requested_output_ids.issubset(allowed_output_ids):
        raise ManufacturingConflict("المنتج النهائي غير مرتبط بالخلطة المختارة")
    products = _load_products(
        db,
        requested_output_ids | {item.product_id for item in payload.scrap_inputs},
        lock=True,
    )
    if set(products) != requested_output_ids | {item.product_id for item in payload.scrap_inputs}:
        raise ManufacturingNotFound("أحد منتجات أمر التصنيع غير موجود")
    if any(products[item_id].standard_weight_kg <= 0 for item_id in requested_output_ids):
        raise ManufacturingConflict("سجل الوزن القياسي لكل منتج نهائي")
    if any(
        products[item.product_id].product_type != "waste" or not products[item.product_id].is_active
        for item in payload.scrap_inputs
    ):
        raise ManufacturingConflict("مصدر كسر المصنع غير موجود أو غير نشط")
    output_snapshot = [
        (
            item.product_id,
            quantity(item.quantity),
            quantity(products[item.product_id].standard_weight_kg),
        )
        for item in payload.outputs
    ]
    material_snapshot = [
        (item.product_id, "material", quantity(item.quantity_per_batch))
        for item in recipe_components
    ] + [
        (item.product_id, "scrap", quantity(item.quantity_per_batch))
        for item in payload.scrap_inputs
    ]
    plan = calculate_batch_plan(
        targets=[
            target(index, planned_quantity, standard_weight)
            for index, (_, planned_quantity, standard_weight) in enumerate(output_snapshot)
        ],
        material_quantities_kg=[item.quantity_per_batch for item in recipe_components],
        reused_scrap_quantities_kg=[item.quantity_per_batch for item in payload.scrap_inputs],
    )
    return output_snapshot, material_snapshot, plan


def create_order(
    db: Session,
    *,
    payload: CreateManufacturingOrderRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> ManufacturingOrderView:
    digest = _request_hash(payload)
    existing = db.scalar(
        select(ManufacturingOrder).where(
            ManufacturingOrder.create_idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if existing.create_request_hash != digest:
            raise ManufacturingConflict("مفتاح منع التكرار مستخدم لأمر تصنيع مختلف")
        return _order_view(db, existing)
    recipe = db.scalar(
        select(ManufacturingRecipe)
        .where(ManufacturingRecipe.id == payload.recipe_id)
        .with_for_update()
    )
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if recipe is None or not recipe.is_active:
        raise ManufacturingNotFound("الخلطة غير موجودة أو غير نشطة")
    if warehouse is None or not warehouse.is_active:
        raise ManufacturingNotFound("المخزن غير موجود أو غير نشط")
    output_snapshot, material_snapshot, plan = _order_snapshot(db, recipe=recipe, payload=payload)
    order = ManufacturingOrder(
        order_number=allocate_document_number(db, "manufacturing_order"),
        recipe_id=recipe.id,
        warehouse_id=payload.warehouse_id,
        status="draft",
        order_date=datetime.now(UTC),
        planned_batches=plan.batches,
        issued_batches=0,
        actual_batches=0,
        target_weight_kg=plan.target_weight_kg,
        planned_input_weight_kg=plan.planned_input_weight_kg,
        returned_scrap_quantity=Decimal("0"),
        material_cost=Decimal("0"),
        finished_cost=Decimal("0"),
        weight_variance_kg=Decimal("0"),
        notes=payload.notes.strip(),
        create_idempotency_key=idempotency_key,
        create_request_hash=digest,
        created_by_id=actor.user.id,
        version=1,
    )
    db.add(order)
    db.flush()
    db.add_all(
        [
            ManufacturingOrderOutput(
                manufacturing_order_id=order.id,
                product_id=product_id,
                planned_quantity=planned_quantity,
                standard_weight_kg=standard_weight,
                good_quantity=Decimal("0"),
                defective_quantity=Decimal("0"),
                actual_weight_kg=Decimal("0"),
                unit_cost=Decimal("0"),
                line_cost=Decimal("0"),
            )
            for product_id, planned_quantity, standard_weight in output_snapshot
        ]
    )
    db.add_all(
        [
            ManufacturingOrderMaterial(
                manufacturing_order_id=order.id,
                product_id=product_id,
                component_kind=kind,
                quantity_per_batch=per_batch,
                planned_quantity=quantity(per_batch * Decimal(plan.batches)),
                issued_quantity=Decimal("0"),
                used_quantity=Decimal("0"),
                returned_quantity=Decimal("0"),
                issued_cost=Decimal("0"),
                used_cost=Decimal("0"),
            )
            for product_id, kind, per_batch in material_snapshot
        ]
    )
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.create",
        entity_type="manufacturing_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={"order_number": order.order_number, "planned_batches": plan.batches},
    )
    return _order_view(db, order)


def _replace_draft_order(
    db: Session,
    *,
    order: ManufacturingOrder,
    payload: UpdateManufacturingOrderRequest,
) -> None:
    recipe = db.scalar(
        select(ManufacturingRecipe)
        .where(ManufacturingRecipe.id == payload.recipe_id)
        .with_for_update()
    )
    warehouse = db.get(Warehouse, payload.warehouse_id)
    if recipe is None or not recipe.is_active:
        raise ManufacturingNotFound("الخلطة غير موجودة أو غير نشطة")
    if warehouse is None or not warehouse.is_active:
        raise ManufacturingNotFound("المخزن غير موجود أو غير نشط")
    output_snapshot, material_snapshot, plan = _order_snapshot(db, recipe=recipe, payload=payload)
    db.execute(
        delete(ManufacturingOrderOutput).where(
            ManufacturingOrderOutput.manufacturing_order_id == order.id
        )
    )
    db.execute(
        delete(ManufacturingOrderMaterial).where(
            ManufacturingOrderMaterial.manufacturing_order_id == order.id
        )
    )
    order.recipe_id = recipe.id
    order.warehouse_id = payload.warehouse_id
    order.planned_batches = plan.batches
    order.target_weight_kg = plan.target_weight_kg
    order.planned_input_weight_kg = plan.planned_input_weight_kg
    order.notes = payload.notes.strip()
    order.version += 1
    db.add_all(
        [
            ManufacturingOrderOutput(
                manufacturing_order_id=order.id,
                product_id=product_id,
                planned_quantity=planned_quantity,
                standard_weight_kg=standard_weight,
                good_quantity=Decimal("0"),
                defective_quantity=Decimal("0"),
                actual_weight_kg=Decimal("0"),
                unit_cost=Decimal("0"),
                line_cost=Decimal("0"),
            )
            for product_id, planned_quantity, standard_weight in output_snapshot
        ]
    )
    db.add_all(
        [
            ManufacturingOrderMaterial(
                manufacturing_order_id=order.id,
                product_id=product_id,
                component_kind=kind,
                quantity_per_batch=per_batch,
                planned_quantity=quantity(per_batch * Decimal(plan.batches)),
                issued_quantity=Decimal("0"),
                used_quantity=Decimal("0"),
                returned_quantity=Decimal("0"),
                issued_cost=Decimal("0"),
                used_cost=Decimal("0"),
            )
            for product_id, kind, per_batch in material_snapshot
        ]
    )


def update_order(
    db: Session,
    *,
    order_id: UUID,
    payload: UpdateManufacturingOrderRequest,
    actor: Principal,
    client: ClientContext,
) -> ManufacturingOrderView:
    order = db.scalar(
        select(ManufacturingOrder).where(ManufacturingOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.status != "draft":
        raise ManufacturingConflict("يمكن تعديل أمر تصنيع في حالة المسودة فقط")
    if order.version != payload.version:
        raise ManufacturingConflict("تم تعديل الأمر بواسطة مستخدم آخر؛ حدّث الصفحة")
    before: dict[str, object] = {
        "version": order.version,
        "planned_batches": order.planned_batches,
    }
    _replace_draft_order(db, order=order, payload=payload)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.update",
        entity_type="manufacturing_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state={"version": order.version, "planned_batches": order.planned_batches},
    )
    return _order_view(db, order)


def delete_draft_order(
    db: Session,
    *,
    order_id: UUID,
    version: int,
    actor: Principal,
    client: ClientContext,
) -> None:
    order = db.scalar(
        select(ManufacturingOrder).where(ManufacturingOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.status != "draft":
        raise ManufacturingConflict("يمكن حذف أمر تصنيع في حالة المسودة فقط")
    if order.version != version:
        raise ManufacturingConflict("تم تعديل الأمر بواسطة مستخدم آخر؛ حدّث الصفحة")
    number = order.order_number
    db.delete(order)
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.delete",
        entity_type="manufacturing_order",
        entity_id=str(order_id),
        outcome="success",
        client=client,
        before_state={"order_number": number, "status": "draft"},
    )


def _stock_aware_plan(
    db: Session,
    *,
    order: ManufacturingOrder,
    lock: bool,
) -> ReplanView:
    material_statement = (
        select(ManufacturingOrderMaterial)
        .where(ManufacturingOrderMaterial.manufacturing_order_id == order.id)
        .order_by(ManufacturingOrderMaterial.created_at, ManufacturingOrderMaterial.id)
    )
    if lock:
        material_statement = material_statement.with_for_update()
    materials = list(db.scalars(material_statement))
    base_weight = sum(
        (
            item.quantity_per_batch
            for item in materials
            if item.component_kind == "material"
        ),
        Decimal("0"),
    )
    scraps = [item for item in materials if item.component_kind == "scrap"]
    available = [
        _available_quantity(db, item.product_id, order.warehouse_id, lock=lock)
        for item in scraps
    ]
    plan = replan_for_available_scrap(
        target_weight_kg=order.target_weight_kg,
        base_material_kg_per_batch=base_weight,
        scrap_quantities_kg_per_batch=[item.quantity_per_batch for item in scraps],
        available_scrap_quantities_kg=available,
        old_batches=order.planned_batches,
    )
    return ReplanView(
        changed=plan.changed,
        old_batches=plan.old_batches,
        new_batches=plan.new_batches,
        target_weight_kg=plan.target_weight_kg,
        planned_scrap_kg=plan.planned_scrap_kg,
        usable_scrap_kg=plan.usable_scrap_kg,
        planned_input_weight_kg=plan.planned_input_weight_kg,
        expected_overage_kg=plan.expected_overage_kg,
    )


def preview_replan(db: Session, order_id: UUID) -> ReplanView:
    order = db.get(ManufacturingOrder, order_id)
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.status != "draft":
        raise ManufacturingConflict("يمكن إعادة تخطيط أمر التصنيع وهو مسودة فقط")
    return _stock_aware_plan(db, order=order, lock=False)


def apply_replan(
    db: Session,
    *,
    order_id: UUID,
    payload: TransitionRequest,
    actor: Principal,
    client: ClientContext,
) -> ManufacturingOrderView:
    order = db.scalar(
        select(ManufacturingOrder)
        .where(ManufacturingOrder.id == order_id)
        .with_for_update()
    )
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.status != "draft":
        raise ManufacturingConflict("يمكن إعادة تخطيط أمر التصنيع وهو مسودة فقط")
    if order.version != payload.version:
        raise ManufacturingConflict("تم تعديل الأمر بواسطة مستخدم آخر؛ حدّث الصفحة")
    result = _stock_aware_plan(db, order=order, lock=True)
    materials = list(
        db.scalars(
            select(ManufacturingOrderMaterial).where(
                ManufacturingOrderMaterial.manufacturing_order_id == order.id
            )
        )
    )
    for item in materials:
        item.planned_quantity = quantity(
            item.quantity_per_batch * Decimal(result.new_batches)
        )
    old_batches = order.planned_batches
    order.planned_batches = result.new_batches
    order.planned_input_weight_kg = result.planned_input_weight_kg
    order.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.replan",
        entity_type="manufacturing_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        before_state={"planned_batches": old_batches},
        after_state={
            "planned_batches": order.planned_batches,
            "usable_scrap_kg": str(result.usable_scrap_kg),
        },
    )
    return _order_view(db, order)


def _available_quantity(
    db: Session,
    product_id: UUID,
    warehouse_id: UUID,
    *,
    lock: bool = True,
) -> Decimal:
    statement = select(InventoryBalance).where(
        InventoryBalance.product_id == product_id,
        InventoryBalance.warehouse_id == warehouse_id,
    )
    if lock:
        statement = statement.with_for_update()
    balance = db.scalar(statement)
    return balance.quantity_on_hand if balance else Decimal("0")


def _issue_batches(
    db: Session,
    *,
    order: ManufacturingOrder,
    materials: list[ManufacturingOrderMaterial],
    batch_count: int,
    operation_key: str,
    issue_kind: str,
    actor: Principal,
    client: ClientContext,
) -> None:
    for item in sorted(materials, key=lambda row: str(row.product_id)):
        requested = quantity(item.quantity_per_batch * Decimal(batch_count))
        issue_quantity = requested
        if item.component_kind == "scrap":
            issue_quantity = min(
                requested, _available_quantity(db, item.product_id, order.warehouse_id)
            )
        if issue_quantity <= 0:
            continue
        transaction = post_issue(
            db,
            payload=IssueRequest(
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                amount=issue_quantity,
                cost_basis="quantity",
                reference_type="manufacturing_material_issue",
                reference_id=str(order.id),
                reference_line_id=str(item.id),
                notes=f"صرف خامات أمر التصنيع {order.order_number}",
            ),
            idempotency_key=_derived_key(operation_key, item.id, issue_kind),
            actor_user_id=actor.user.id,
            client=client,
            transaction_type="production_issue",
        )
        db.add(
            ManufacturingMaterialIssue(
                order_material_id=item.id,
                inventory_transaction_id=transaction.id,
                issue_kind=issue_kind,
                batch_count=batch_count,
                quantity=-transaction.quantity_delta,
                weight_kg=-transaction.weight_delta_kg,
                total_cost=money(transaction.total_cost),
            )
        )
        item.issued_quantity = quantity(item.issued_quantity - transaction.quantity_delta)
        item.issued_cost = money(item.issued_cost + transaction.total_cost)


def start_order(
    db: Session,
    *,
    order_id: UUID,
    payload: TransitionRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> ManufacturingOrderView:
    digest = _request_hash(payload)
    order = db.scalar(
        select(ManufacturingOrder).where(ManufacturingOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.start_idempotency_key == idempotency_key:
        if order.start_request_hash != digest:
            raise ManufacturingConflict("مفتاح منع التكرار مستخدم لطلب بدء مختلف")
        return _order_view(db, order)
    if order.status != "draft":
        raise ManufacturingConflict("يمكن بدء أمر تصنيع في حالة المسودة فقط")
    if order.version != payload.version:
        raise ManufacturingConflict("تم تعديل الأمر بواسطة مستخدم آخر؛ حدّث الصفحة")
    materials = list(
        db.scalars(
            select(ManufacturingOrderMaterial)
            .where(ManufacturingOrderMaterial.manufacturing_order_id == order.id)
            .with_for_update()
        )
    )
    _issue_batches(
        db,
        order=order,
        materials=materials,
        batch_count=order.planned_batches,
        operation_key=idempotency_key,
        issue_kind="initial",
        actor=actor,
        client=client,
    )
    order.status = "in_progress"
    order.issued_batches = order.planned_batches
    order.material_cost = money(sum((item.issued_cost for item in materials), Decimal("0")))
    order.start_idempotency_key = idempotency_key
    order.start_request_hash = digest
    order.started_by_id = actor.user.id
    order.started_at = datetime.now(UTC)
    order.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.start",
        entity_type="manufacturing_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={
            "issued_batches": order.issued_batches,
            "material_cost": str(order.material_cost),
        },
    )
    return _order_view(db, order)


def _complete_outputs(
    db: Session,
    *,
    order: ManufacturingOrder,
    completion: ManufacturingCompletion,
    order_outputs: list[ManufacturingOrderOutput],
    plan: CompletionPlan,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> None:
    costs = {item.product_id: item for item in plan.outputs}
    for row in order_outputs:
        result = costs[str(row.product_id)]
        inventory_transaction_id = None
        if result.good_quantity > 0:
            receipt = post_receipt(
                db,
                payload=ReceiptRequest(
                    product_id=row.product_id,
                    warehouse_id=order.warehouse_id,
                    quantity=result.good_quantity,
                    weight_kg=result.actual_weight_kg,
                    cost_basis="weight",
                    unit_cost=plan.cost_per_good_kg,
                    lot_number=f"{order.order_number}-FG-{row.product_id}",
                    reference_type="manufacturing_output",
                    reference_id=str(order.id),
                    reference_line_id=str(row.id),
                    notes=f"إنتاج تام {order.order_number}",
                ),
                idempotency_key=_derived_key(idempotency_key, row.id, "output"),
                actor_user_id=actor.user.id,
                client=client,
                transaction_type="production_output",
            )
            inventory_transaction_id = receipt.id
        row.good_quantity = result.good_quantity
        row.defective_quantity = result.defective_quantity
        row.actual_weight_kg = result.actual_weight_kg
        row.unit_cost = result.unit_cost
        row.line_cost = result.line_cost
        row.inventory_transaction_id = inventory_transaction_id
        db.add(
            ManufacturingCompletionOutput(
                completion_id=completion.id,
                product_id=row.product_id,
                good_quantity=result.good_quantity,
                defective_quantity=result.defective_quantity,
                actual_weight_kg=result.actual_weight_kg,
                line_cost=result.line_cost,
                unit_cost=result.unit_cost,
                inventory_transaction_id=inventory_transaction_id,
            )
        )


def complete_order(
    db: Session,
    *,
    order_id: UUID,
    payload: CompleteManufacturingOrderRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> ManufacturingOrderView:
    digest = _request_hash(payload)
    order = db.scalar(
        select(ManufacturingOrder).where(ManufacturingOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.completion_idempotency_key == idempotency_key:
        if order.completion_request_hash != digest:
            raise ManufacturingConflict("مفتاح منع التكرار مستخدم لإكمال مختلف")
        return _order_view(db, order)
    if order.status != "in_progress":
        raise ManufacturingConflict("يمكن إتمام أمر تصنيع جارٍ فقط")
    if order.version != payload.version:
        raise ManufacturingConflict("تم تعديل الأمر بواسطة مستخدم آخر؛ حدّث الصفحة")
    materials = list(
        db.scalars(
            select(ManufacturingOrderMaterial)
            .where(ManufacturingOrderMaterial.manufacturing_order_id == order.id)
            .order_by(ManufacturingOrderMaterial.created_at, ManufacturingOrderMaterial.id)
            .with_for_update()
        )
    )
    if payload.actual_batches > order.issued_batches:
        additional = payload.actual_batches - order.issued_batches
        _issue_batches(
            db,
            order=order,
            materials=materials,
            batch_count=additional,
            operation_key=idempotency_key,
            issue_kind="additional",
            actor=actor,
            client=client,
        )
        order.issued_batches = payload.actual_batches
        db.flush()
    order_outputs = list(
        db.scalars(
            select(ManufacturingOrderOutput)
            .where(ManufacturingOrderOutput.manufacturing_order_id == order.id)
            .order_by(ManufacturingOrderOutput.created_at, ManufacturingOrderOutput.id)
            .with_for_update()
        )
    )
    supplied_outputs = {item.product_id: item for item in payload.outputs}
    if set(supplied_outputs).difference({item.product_id for item in order_outputs}):
        raise ManufacturingConflict("تفاصيل الإنتاج تحتوي منتجًا لا يخص الأمر")
    products = _load_products(db, {item.product_id for item in materials})
    output_products = _load_products(db, {item.product_id for item in order_outputs})
    completion_outputs: list[CompletionOutput] = []
    for output_row in order_outputs:
        supplied = supplied_outputs.get(output_row.product_id)
        completion_outputs.append(
            CompletionOutput(
                product_id=str(output_row.product_id),
                name=output_products[output_row.product_id].name_ar,
                good_quantity=supplied.good_quantity if supplied else Decimal("0"),
                defective_quantity=(supplied.defective_quantity if supplied else Decimal("0")),
                actual_weight_kg=(supplied.actual_weight_kg if supplied else Decimal("0")),
            )
        )
    plan = calculate_completion_plan(
        actual_batches=payload.actual_batches,
        issued_batches=order.issued_batches,
        materials=[
            CompletionMaterial(
                product_id=str(item.product_id),
                name=products[item.product_id].name_ar,
                component_kind=item.component_kind,
                quantity_per_batch=item.quantity_per_batch,
                issued_quantity=item.issued_quantity,
                unit_cost=(
                    quantity(item.issued_cost / item.issued_quantity)
                    if item.issued_quantity > 0
                    else Decimal("0")
                ),
            )
            for item in materials
        ],
        outputs=completion_outputs,
        scrap_weight_kg=payload.scrap_weight_kg,
        adjustments=[
            MixAdjustment(
                excluded_product_id=str(item.excluded_product_id),
                batch_count=item.batch_count,
                reason=item.reason,
                actual_material_quantities={
                    str(value.product_id): value.actual_quantity
                    for value in item.actual_material_quantities
                },
            )
            for item in payload.adjustments
        ],
    )
    completion = ManufacturingCompletion(
        manufacturing_order_id=order.id,
        idempotency_key=idempotency_key,
        request_hash=digest,
        actual_batches=plan.actual_batches,
        full_batches=plan.full_batches,
        modified_batches=plan.modified_batches,
        good_output_quantity=plan.good_output_quantity,
        defective_output_quantity=plan.defective_output_quantity,
        actual_output_weight_kg=plan.actual_output_weight_kg,
        scrap_weight_kg=plan.scrap_weight_kg,
        used_input_weight_kg=plan.used_input_weight_kg,
        full_mix_cost=plan.full_mix_cost,
        modified_mix_cost=plan.modified_mix_cost,
        total_material_cost=plan.total_material_cost,
        average_input_cost_per_kg=plan.average_input_cost_per_kg,
        scrap_value=plan.scrap_value,
        finished_cost=plan.finished_cost,
        cost_per_good_kg=plan.cost_per_good_kg,
        weight_variance_kg=plan.weight_variance_kg,
        notes=payload.notes.strip(),
        completed_by_id=actor.user.id,
    )
    db.add(completion)
    db.flush()
    usage = {item.product_id: item for item in plan.materials}
    for item in materials:
        result = usage[str(item.product_id)]
        if result.unused_quantity > 0:
            returned = post_receipt(
                db,
                payload=ReceiptRequest(
                    product_id=item.product_id,
                    warehouse_id=order.warehouse_id,
                    quantity=result.unused_quantity,
                    weight_kg=Decimal("0"),
                    cost_basis="quantity",
                    unit_cost=result.unit_cost,
                    reference_type="manufacturing_unused_return",
                    reference_id=str(order.id),
                    reference_line_id=str(item.id),
                    notes=f"رد خامات غير مستخدمة عند إتمام {order.order_number}",
                ),
                idempotency_key=_derived_key(idempotency_key, item.id, "unused-return"),
                actor_user_id=actor.user.id,
                client=client,
                transaction_type="return_in",
            )
            item.return_inventory_transaction_id = returned.id
        item.used_quantity = result.used_quantity
        item.returned_quantity = result.unused_quantity
        item.used_cost = result.used_cost
    _complete_outputs(
        db,
        order=order,
        completion=completion,
        order_outputs=order_outputs,
        plan=plan,
        idempotency_key=idempotency_key,
        actor=actor,
        client=client,
    )
    recipe = db.get(ManufacturingRecipe, order.recipe_id)
    if recipe is None:
        raise ManufacturingNotFound("خلطة أمر التصنيع غير موجودة")
    if plan.scrap_weight_kg > 0:
        scrap_receipt = post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=recipe.scrap_product_id,
                warehouse_id=order.warehouse_id,
                quantity=plan.scrap_weight_kg,
                weight_kg=Decimal("0"),
                cost_basis="quantity",
                unit_cost=plan.average_input_cost_per_kg,
                lot_number=f"{order.order_number}-SCRAP",
                reference_type="manufacturing_scrap",
                reference_id=str(order.id),
                notes=f"هالك مصنع ناتج من {order.order_number}",
            ),
            idempotency_key=_derived_key(idempotency_key, completion.id, "scrap-output"),
            actor_user_id=actor.user.id,
            client=client,
            transaction_type="production_output",
        )
        completion.scrap_inventory_transaction_id = scrap_receipt.id
    for adjustment_result in plan.adjustments:
        adjustment = ManufacturingMixAdjustment(
            completion_id=completion.id,
            excluded_product_id=UUID(adjustment_result.excluded_product_id),
            batch_count=adjustment_result.batch_count,
            reason=adjustment_result.reason,
            cost_amount=adjustment_result.cost_amount,
        )
        db.add(adjustment)
        db.flush()
        db.add_all(
            [
                ManufacturingMixAdjustmentMaterial(
                    adjustment_id=adjustment.id,
                    product_id=UUID(product_id),
                    actual_quantity=actual_quantity,
                )
                for product_id, actual_quantity in (
                    adjustment_result.actual_material_quantities.items()
                )
            ]
        )
    order.status = "completed"
    order.actual_batches = plan.actual_batches
    order.returned_scrap_quantity = plan.scrap_weight_kg
    order.material_cost = plan.total_material_cost
    order.finished_cost = plan.finished_cost
    order.weight_variance_kg = plan.weight_variance_kg
    order.completion_idempotency_key = idempotency_key
    order.completion_request_hash = digest
    order.completed_by_id = actor.user.id
    order.completed_at = datetime.now(UTC)
    order.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.complete",
        entity_type="manufacturing_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={
            "actual_batches": plan.actual_batches,
            "material_cost": str(plan.total_material_cost),
            "finished_cost": str(plan.finished_cost),
            "scrap_weight_kg": str(plan.scrap_weight_kg),
        },
    )
    return _order_view(db, order)


def cancel_order(
    db: Session,
    *,
    order_id: UUID,
    payload: CancelManufacturingOrderRequest,
    idempotency_key: str,
    actor: Principal,
    client: ClientContext,
) -> ManufacturingOrderView:
    order = db.scalar(
        select(ManufacturingOrder).where(ManufacturingOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    if order.cancellation_idempotency_key == idempotency_key:
        return _order_view(db, order)
    if order.status != "in_progress":
        raise ManufacturingConflict("يمكن إلغاء أمر تصنيع جارٍ فقط")
    if order.version != payload.version:
        raise ManufacturingConflict("تم تعديل الأمر بواسطة مستخدم آخر؛ حدّث الصفحة")
    materials = {
        item.id: item
        for item in db.scalars(
            select(ManufacturingOrderMaterial)
            .where(ManufacturingOrderMaterial.manufacturing_order_id == order.id)
            .with_for_update()
        )
    }
    issues = list(
        db.scalars(
            select(ManufacturingMaterialIssue)
            .where(ManufacturingMaterialIssue.order_material_id.in_(set(materials)))
            .order_by(ManufacturingMaterialIssue.created_at, ManufacturingMaterialIssue.id)
            .with_for_update()
        )
    )
    for issue in issues:
        item = materials[issue.order_material_id]
        reversal = post_receipt(
            db,
            payload=ReceiptRequest(
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                quantity=issue.quantity,
                weight_kg=issue.weight_kg,
                cost_basis="quantity",
                unit_cost=quantity(issue.total_cost / issue.quantity),
                reference_type="manufacturing_cancel",
                reference_id=str(order.id),
                reference_line_id=str(issue.id),
                notes=payload.reason,
            ),
            idempotency_key=_derived_key(idempotency_key, issue.id, "cancel-return"),
            actor_user_id=actor.user.id,
            client=client,
            transaction_type="reversal_in",
            reversal_of_id=issue.inventory_transaction_id,
        )
        issue.reversal_transaction_id = reversal.id
    for item in materials.values():
        item.returned_quantity = item.issued_quantity
    order.status = "cancelled"
    order.cancellation_idempotency_key = idempotency_key
    order.cancellation_reason = payload.reason.strip()
    order.cancelled_by_id = actor.user.id
    order.cancelled_at = datetime.now(UTC)
    order.version += 1
    db.flush()
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="manufacturing.order.cancel",
        entity_type="manufacturing_order",
        entity_id=str(order.id),
        outcome="success",
        client=client,
        after_state={"reason": order.cancellation_reason},
    )
    return _order_view(db, order)


def list_orders(db: Session, *, limit: int = 200) -> list[ManufacturingOrderView]:
    statement = (
        select(ManufacturingOrder)
        .order_by(ManufacturingOrder.order_date.desc(), ManufacturingOrder.id.desc())
        .limit(limit)
    )
    return [_order_view(db, item) for item in db.scalars(statement)]


def get_order(db: Session, order_id: UUID) -> ManufacturingOrderView:
    order = db.get(ManufacturingOrder, order_id)
    if order is None:
        raise ManufacturingNotFound("أمر التصنيع غير موجود")
    return _order_view(db, order)


def manufacturing_options(db: Session) -> ManufacturingOptionsView:
    recipes = list(
        db.scalars(
            select(ManufacturingRecipe)
            .where(ManufacturingRecipe.is_active.is_(True))
            .order_by(ManufacturingRecipe.code)
        )
    )
    warehouses = list(
        db.scalars(select(Warehouse).where(Warehouse.is_active.is_(True)).order_by(Warehouse.code))
    )
    products = list(
        db.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.code))
    )

    def option(item: Product) -> ManufacturingOption:
        return ManufacturingOption(
            id=item.id,
            code=item.code,
            name_ar=item.name_ar,
            product_type=item.product_type,
            standard_weight_kg=item.standard_weight_kg,
        )

    return ManufacturingOptionsView(
        recipes=[
            ManufacturingOption(id=item.id, code=item.code, name_ar=item.name_ar)
            for item in recipes
        ],
        warehouses=[
            ManufacturingOption(id=item.id, code=item.code, name_ar=item.name_ar)
            for item in warehouses
        ],
        output_products=[option(item) for item in products if item.product_type == "finished_good"],
        material_products=[
            option(item) for item in products if item.product_type in {"raw_material", "waste"}
        ],
        scrap_products=[option(item) for item in products if item.product_type == "waste"],
    )
