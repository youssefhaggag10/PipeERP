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


def _validate_lines(lines: list[WeightCardLine]) -> tuple[Decimal, Decimal]:
    if not lines:
        raise ValueError("أضف بندًا واحدًا على الأقل")
    if any(line.pieces <= 0 or line.standard_weight_kg < 0 for line in lines):
        raise ValueError("الكميات والأوزان القياسية غير صحيحة")
    total_pieces = sum((line.pieces for line in lines), Decimal("0"))
    theoretical_total = sum((line.theoretical_weight_kg for line in lines), Decimal("0"))
    return total_pieces, theoretical_total


def _allocate_total_weight(
    lines: list[WeightCardLine],
    *,
    total_weight: Decimal,
    total_pieces: Decimal,
    theoretical_total: Decimal,
) -> list[Decimal]:
    remaining = total_weight
    allocated: list[Decimal] = []
    denominator = theoretical_total if theoretical_total > 0 else total_pieces
    for index, item in enumerate(lines):
        if index == len(lines) - 1:
            line_weight = remaining
        else:
            basis = item.theoretical_weight_kg if theoretical_total > 0 else item.pieces
            line_weight = min(quantity(total_weight * basis / denominator), remaining)
        allocated.append(line_weight)
        remaining -= line_weight
    return allocated


def _allocate_weights(
    lines: list[WeightCardLine],
    *,
    weight_mode: WeightMode,
    total_actual_weight_kg: Decimal | None,
    total_pieces: Decimal,
    theoretical_total: Decimal,
) -> tuple[list[Decimal], Decimal]:
    if weight_mode == "total_card":
        if total_actual_weight_kg is None or total_actual_weight_kg <= 0:
            raise ValueError("أدخل وزن الكارتة الفعلي")
        total_weight = quantity(total_actual_weight_kg)
        return (
            _allocate_total_weight(
                lines,
                total_weight=total_weight,
                total_pieces=total_pieces,
                theoretical_total=theoretical_total,
            ),
            total_weight,
        )
    if weight_mode == "per_line":
        if any(item.actual_weight_kg is None or item.actual_weight_kg <= 0 for item in lines):
            raise ValueError("أدخل الوزن الفعلي لكل بند")
        allocated = [quantity(item.actual_weight_kg or Decimal("0")) for item in lines]
        return allocated, sum(allocated, Decimal("0"))
    raise ValueError("طريقة الوزن غير صحيحة")


def _resolve_prices(
    lines: list[WeightCardLine],
    *,
    pricing_mode: PricingMode,
    total_weight: Decimal,
    uniform_price_per_kg: Decimal | None,
) -> tuple[list[Decimal], Decimal | None]:
    if pricing_mode == "uniform":
        if uniform_price_per_kg is None or uniform_price_per_kg < 0:
            raise ValueError("سعر الكيلو الموحد غير صحيح")
        return (
            [uniform_price_per_kg] * len(lines),
            money(total_weight * uniform_price_per_kg),
        )
    if pricing_mode == "per_line":
        if any(item.price_per_kg is None or item.price_per_kg < 0 for item in lines):
            raise ValueError("أدخل سعر الكيلو لكل بند")
        return [item.price_per_kg or Decimal("0") for item in lines], None
    raise ValueError("طريقة التسعير غير صحيحة")


def _price_lines(
    lines: list[WeightCardLine],
    allocated: list[Decimal],
    prices: list[Decimal],
    expected_total: Decimal | None,
) -> tuple[list[PricedWeightLine], Decimal]:
    result: list[PricedWeightLine] = []
    subtotal = Decimal("0")
    for index, (item, line_weight, price) in enumerate(zip(lines, allocated, prices, strict=True)):
        is_final_uniform_line = expected_total is not None and index == len(lines) - 1
        line_total = (
            expected_total - subtotal
            if is_final_uniform_line and expected_total is not None
            else money(line_weight * price)
        )
        subtotal += line_total
        result.append(
            PricedWeightLine(
                product_id=item.product_id,
                pieces=item.pieces,
                standard_weight_kg=item.standard_weight_kg,
                theoretical_weight_kg=quantity(item.theoretical_weight_kg),
                allocated_weight_kg=line_weight,
                price_per_kg=price,
                line_total=line_total,
            )
        )
    return result, subtotal


def calculate_weight_card(
    *,
    lines: list[WeightCardLine],
    weight_mode: WeightMode,
    pricing_mode: PricingMode,
    total_actual_weight_kg: Decimal | None = None,
    uniform_price_per_kg: Decimal | None = None,
) -> WeightCardTotals:
    total_pieces, theoretical_total = _validate_lines(lines)
    allocated, total_weight = _allocate_weights(
        lines,
        weight_mode=weight_mode,
        total_actual_weight_kg=total_actual_weight_kg,
        total_pieces=total_pieces,
        theoretical_total=theoretical_total,
    )
    prices, expected_total = _resolve_prices(
        lines,
        pricing_mode=pricing_mode,
        total_weight=total_weight,
        uniform_price_per_kg=uniform_price_per_kg,
    )
    result, subtotal = _price_lines(lines, allocated, prices, expected_total)

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
            as_decimal(price_per_kg, field="سعر الكيلو") if price_per_kg is not None else None
        ),
    )
