from __future__ import annotations


def normalized_phone_numbers(value: object) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for line in str(value or "").splitlines():
        phone = line.strip()
        if phone and phone not in seen:
            result.append(phone)
            seen.add(phone)
    return result


def footer_phone_text(value: object) -> tuple[str, str]:
    phones = normalized_phone_numbers(value)
    if not phones:
        return "", ""
    main_phone = phones[0]
    sales_text = ""
    if len(phones) > 1:
        sales_text = f"إدارة المبيعات: {' | '.join(phones[1:])}"
    return main_phone, sales_text


__all__ = ["footer_phone_text", "normalized_phone_numbers"]
