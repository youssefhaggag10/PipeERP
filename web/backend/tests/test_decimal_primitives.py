from app.domain.common.decimal import as_decimal


def test_as_decimal_rejects_text_and_non_finite_values() -> None:
    for value in ("not-a-number", "NaN", "Infinity"):
        try:
            as_decimal(value, field="القيمة")
        except ValueError as exc:
            assert "القيمة" in str(exc)
        else:
            raise AssertionError("Expected ValueError")
