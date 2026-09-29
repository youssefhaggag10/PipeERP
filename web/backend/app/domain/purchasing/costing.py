from dataclasses import dataclass
from decimal import Decimal

from app.domain.common.decimal import money, quantity


@dataclass(frozen=True, slots=True)
class PurchaseReceiptCost:
    gross_amount: Decimal
    loss_amount: Decimal
    net_amount: Decimal
    goods_cost: Decimal
    additional_cost: Decimal
    capitalized_cost: Decimal
    inventory_unit_cost: Decimal


def calculate_receipt_cost(
    *,
    gross_amount: Decimal,
    loss_amount: Decimal,
    unit_price: Decimal,
    additional_unit_cost: Decimal = Decimal("0"),
) -> PurchaseReceiptCost:
    gross = quantity(gross_amount)
    loss = quantity(loss_amount)
    if gross <= 0:
        raise ValueError("الكمية المستلمة يجب أن تكون أكبر من صفر")
    if loss < 0 or loss >= gross:
        raise ValueError("الفاقد يجب أن يكون صفرًا أو أقل من الكمية المستلمة")
    if unit_price < 0 or additional_unit_cost < 0:
        raise ValueError("تكلفة الشراء والتكلفة الإضافية لا يمكن أن تكونا سالبتين")

    net = quantity(gross - loss)
    goods_cost = money(gross * unit_price)
    additional_cost = money(gross * additional_unit_cost)
    capitalized_cost = money(goods_cost + additional_cost)
    return PurchaseReceiptCost(
        gross_amount=gross,
        loss_amount=loss,
        net_amount=net,
        goods_cost=goods_cost,
        additional_cost=additional_cost,
        capitalized_cost=capitalized_cost,
        inventory_unit_cost=quantity(capitalized_cost / net),
    )


def validate_partial_receipt(
    *,
    ordered_amount: Decimal,
    previously_received_amount: Decimal,
    current_received_amount: Decimal,
) -> Decimal:
    ordered = quantity(ordered_amount)
    previous = quantity(previously_received_amount)
    current = quantity(current_received_amount)
    if ordered <= 0 or previous < 0 or current <= 0:
        raise ValueError("كميات أمر الشراء والاستلام غير صالحة")
    updated = quantity(previous + current)
    if updated > ordered:
        raise ValueError("الاستلام يتجاوز الكمية المتبقية في أمر الشراء")
    return quantity(ordered - updated)
