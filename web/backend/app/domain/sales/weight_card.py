from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.domain.common.decimal import as_decimal, money, quantity

WeightMode = Literal["total_card", "per_line"]
PricingMode = Literal["uniform", "per_line"]


@dataclass(frozen=True, slots=True)
class WeightCardLine:
    product_id: int
    pieces: Decimal
    standard_weight_kg: Decimal
    actual_weight_kg: Decimal | None = None
    price_per_kg: Decimal | None = None

    @property
    def theoretical_weight_kg(self) -> Decimal:
        return self.pieces * self.standard_weight_kg


@dataclass(frozen=True, slots=True)
class PricedWeightLine:
    product_id: int
    pieces: Decimal
    standard_weight_kg: Decimal
    theoretical_weight_kg: Decimal
    allocated_weight_kg: Decimal
    price_per_kg: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class WeightCardTotals:
    lines: tuple[PricedWeightLine, ...]
    total_pieces: Decimal
    total_weight_kg: Decimal
    subtotal: Decimal


def calculate_weight_card(
    *,
    lines: list[WeightCardLine],
    weight_mode: WeightMode,
    pricing_mode: PricingMode,
    total_actual_weight_kg: Decimal | None = None,
    uniform_price_per_kg: Decimal | None = None,
) -> WeightCardTotals:
    if not lines:
        raise ValueError("أضف بندًا واحدًا على الأقل")
    if any(line.pieces <= 0 or line.standard_weight_kg < 0 for line in lines):
        raise ValueError("الكميات والأوزان القياسية غير صحيحة")

    total_pieces = sum((line.pieces for line in lines), Decimal("0"))
    theoretical_total = sum((line.theoretical_weight_kg for line in lines), Decimal("0"))

    if weight_mode == "total_card":
        if total_actual_weight_kg is None or total_actual_weight_kg <= 0:
            raise ValueError("أدخل وزن الكارتة الفعلي")
        total_weight = quantity(total_actual_weight_kg)
        remaining = total_weight
        allocated: list[Decimal] = []
        for index, line in enumerate(lines):
            if index == len(lines) - 1:
                line_weight = remaining
            else:
                basis = line.theoretical_weight_kg if theoretical_total > 0 else line.pieces
                denominator = theoretical_total if theoretical_total > 0 else total_pieces
                line_weight = min(quantity(total_weight * basis / denominator), remaining)
            allocated.append(line_weight)
            remaining -= line_weight
    elif weight_mode == "per_line":
        if any(line.actual_weight_kg is None or line.actual_weight_kg <= 0 for line in lines):
            raise ValueError("أدخل الوزن الفعلي لكل بند")
        allocated = [quantity(line.actual_weight_kg or Decimal("0")) for line in lines]
        total_weight = sum(allocated, Decimal("0"))
    else:
        raise ValueError("طريقة الوزن غير صحيحة")

    if pricing_mode == "uniform":
        if uniform_price_per_kg is None or uniform_price_per_kg < 0:
            raise ValueError("سعر الكيلو الموحد غير صحيح")
        prices = [uniform_price_per_kg] * len(lines)
        expected_total = money(total_weight * uniform_price_per_kg)
    elif pricing_mode == "per_line":
        if any(line.price_per_kg is None or line.price_per_kg < 0 for line in lines):
            raise ValueError("أدخل سعر الكيلو لكل بند")
        prices = [line.price_per_kg or Decimal("0") for line in lines]
        expected_total = None
    else:
        raise ValueError("طريقة التسعير غير صحيحة")

    result: list[PricedWeightLine] = []
    subtotal = Decimal("0")
    for index, (line, line_weight, price) in enumerate(zip(lines, allocated, prices, strict=True)):
        line_total = (
            expected_total - subtotal
            if expected_total is not None and index == len(lines) - 1
            else money(line_weight * price)
        )
        subtotal += line_total
        result.append(
            PricedWeightLine(
                product_id=line.product_id,
                pieces=line.pieces,
                standard_weight_kg=line.standard_weight_kg,
                theoretical_weight_kg=quantity(line.theoretical_weight_kg),
                allocated_weight_kg=line_weight,
                price_per_kg=price,
                line_total=line_total,
            )
        )

    if sum((item.allocated_weight_kg for item in result), Decimal("0")) != total_weight:
        raise AssertionError("مجموع الأوزان الموزعة لا يساوي وزن الكارتة")

    return WeightCardTotals(
        lines=tuple(result),
        total_pieces=total_pieces,
        total_weight_kg=total_weight,
        subtotal=money(subtotal),
    )


def line(
    product_id: int,
    pieces: object,
    standard_weight_kg: object,
    *,
    actual_weight_kg: object | None = None,
    price_per_kg: object | None = None,
) -> WeightCardLine:
    return WeightCardLine(
        product_id=product_id,
        pieces=as_decimal(pieces, field="الكمية"),
        standard_weight_kg=as_decimal(standard_weight_kg, field="الوزن القياسي"),
        actual_weight_kg=(
            as_decimal(actual_weight_kg, field="الوزن الفعلي")
            if actual_weight_kg is not None
            else None
        ),
        price_per_kg=(
            as_decimal(price_per_kg, field="سعر الكيلو")
            if price_per_kg is not None
            else None
        ),
    )
