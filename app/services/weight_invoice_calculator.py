from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

EPSILON = Decimal("0.0000001")
WEIGHT_QUANTUM = Decimal("0.000001")
MONEY_QUANTUM = Decimal("0.01")


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception as error:
        raise ValueError(f"{field} يجب أن يكون رقمًا صحيحًا") from error


def calculate_net_weight(
    *,
    net_weight_kg: float | None = None,
    use_vehicle_scale: bool = False,
    gross_weight_kg: float | None = None,
    tare_weight_kg: float | None = None,
) -> float:
    if use_vehicle_scale:
        gross = _decimal(gross_weight_kg, field="الوزن القائم")
        tare = _decimal(tare_weight_kg, field="وزن السيارة الفارغ")
        if gross <= EPSILON or tare < 0:
            raise ValueError("أدخل الوزن القائم ووزن السيارة الفارغ بصورة صحيحة")
        net = gross - tare
    else:
        net = _decimal(net_weight_kg, field="الوزن الصافي")
    if net <= EPSILON:
        raise ValueError("الوزن الصافي الفعلي يجب أن يكون أكبر من صفر")
    return float(net.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP))


def calculate_weight_invoice(
    *,
    lines: list[dict],
    weight_mode: str,
    pricing_mode: str,
    total_actual_weight_kg: float | None = None,
    uniform_price_per_kg: float | None = None,
) -> dict:
    """Normalize weight-sale lines and calculate exact commercial totals.

    ``weight_mode`` is ``total_card`` or ``per_line``.
    ``pricing_mode`` is ``uniform`` or ``per_line``.
    The final line absorbs allocation and money rounding remainders so the
    distributed weight and uniform-price total remain exactly equal to the
    values entered for the card.
    """

    if weight_mode not in {"total_card", "per_line"}:
        raise ValueError("طريقة الوزن غير صحيحة")
    if pricing_mode not in {"uniform", "per_line"}:
        raise ValueError("طريقة التسعير غير صحيحة")
    if not lines:
        raise ValueError("أضف بندًا واحدًا على الأقل")

    uniform_price = _decimal(uniform_price_per_kg, field="سعر الكيلو الموحد")
    if pricing_mode == "uniform" and uniform_price < 0:
        raise ValueError("سعر الكيلو لا يمكن أن يكون سالبًا")

    prepared: list[dict] = []
    theoretical_total = Decimal("0")
    quantity_total = Decimal("0")
    for index, source in enumerate(lines, start=1):
        quantity = _decimal(source.get("quantity"), field=f"كمية البند رقم {index}")
        standard = _decimal(
            source.get("standard_weight_kg"),
            field=f"الوزن القياسي للبند رقم {index}",
        )
        if quantity <= EPSILON:
            raise ValueError(f"كمية البند رقم {index} يجب أن تكون أكبر من صفر")
        if standard < 0:
            raise ValueError(f"الوزن القياسي للبند رقم {index} لا يمكن أن يكون سالبًا")
        theoretical = quantity * standard
        quantity_total += quantity
        theoretical_total += theoretical
        prepared.append(
            {
                **source,
                "quantity": quantity,
                "standard_weight_kg": standard,
                "theoretical_weight_kg": theoretical,
            }
        )

    if weight_mode == "total_card":
        total_weight = _decimal(total_actual_weight_kg, field="وزن الكارتة الفعلي")
        if total_weight <= EPSILON:
            raise ValueError("أدخل وزن الكارتة الفعلي")
        remaining = total_weight.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP)
        for index, item in enumerate(prepared):
            if index == len(prepared) - 1:
                allocated = remaining
            else:
                basis = item["theoretical_weight_kg"]
                denominator = theoretical_total
                if denominator <= EPSILON:
                    basis = item["quantity"]
                    denominator = quantity_total
                allocated = (total_weight * basis / denominator).quantize(
                    WEIGHT_QUANTUM,
                    rounding=ROUND_HALF_UP,
                )
                allocated = min(allocated, remaining)
            item["actual_weight_kg"] = allocated
            item["allocated_weight_kg"] = allocated
            remaining -= allocated
    else:
        total_weight = Decimal("0")
        for index, item in enumerate(prepared, start=1):
            actual = _decimal(
                item.get("actual_weight_kg"),
                field=f"الوزن الفعلي للبند رقم {index}",
            )
            if actual <= EPSILON:
                raise ValueError(f"أدخل الوزن الفعلي للبند رقم {index}")
            actual = actual.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP)
            item["actual_weight_kg"] = actual
            item["allocated_weight_kg"] = actual
            total_weight += actual

    expected_weight = total_weight.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP)
    exact_uniform_total = (
        (expected_weight * uniform_price).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if pricing_mode == "uniform"
        else None
    )
    subtotal = Decimal("0")
    normalized: list[dict] = []
    for index, item in enumerate(prepared, start=1):
        price = (
            uniform_price
            if pricing_mode == "uniform"
            else _decimal(item.get("price_per_kg"), field=f"سعر كيلو البند رقم {index}")
        )
        if price < 0:
            raise ValueError(f"سعر كيلو البند رقم {index} لا يمكن أن يكون سالبًا")
        if pricing_mode == "uniform" and index == len(prepared):
            line_total = exact_uniform_total - subtotal
        else:
            line_total = (item["actual_weight_kg"] * price).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
        subtotal += line_total
        normalized.append(
            {
                **item,
                "quantity": float(item["quantity"]),
                "standard_weight_kg": float(item["standard_weight_kg"]),
                "theoretical_weight_kg": float(item["theoretical_weight_kg"]),
                "actual_weight_kg": float(item["actual_weight_kg"]),
                "allocated_weight_kg": float(item["allocated_weight_kg"]),
                "price_per_kg": float(price),
                "line_total": float(line_total),
                "notes": str(item.get("notes") or "").strip(),
            }
        )

    distributed_total = sum(
        (Decimal(str(item["allocated_weight_kg"])) for item in normalized),
        Decimal("0"),
    )
    if distributed_total != expected_weight:
        raise AssertionError("مجموع الأوزان الموزعة لا يساوي الوزن الفعلي")
    if exact_uniform_total is not None and subtotal != exact_uniform_total:
        raise AssertionError("إجمالي البنود لا يساوي وزن الكارتة في سعر الكيلو")

    return {
        "weight_mode": weight_mode,
        "pricing_mode": pricing_mode,
        "lines": normalized,
        "total_pieces": float(quantity_total),
        "total_actual_weight_kg": float(expected_weight),
        "subtotal": float(subtotal.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)),
        "uniform_price_per_kg": float(uniform_price) if pricing_mode == "uniform" else 0.0,
    }


__all__ = ["calculate_net_weight", "calculate_weight_invoice"]
