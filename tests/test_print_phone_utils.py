from app.utils.print_phone_utils import footer_phone_text, normalized_phone_numbers


def test_phone_numbers_support_future_sales_team_members() -> None:
    value = "PHONE-MAIN\nPHONE-SALES-1\nPHONE-SALES-2\nPHONE-SALES-3"

    assert normalized_phone_numbers(value) == [
        "PHONE-MAIN",
        "PHONE-SALES-1",
        "PHONE-SALES-2",
        "PHONE-SALES-3",
    ]
    assert footer_phone_text(value) == (
        "PHONE-MAIN",
        "إدارة المبيعات: PHONE-SALES-1 | PHONE-SALES-2 | PHONE-SALES-3",
    )


def test_phone_numbers_remove_empty_lines_and_duplicates() -> None:
    value = "PHONE-MAIN\n\nPHONE-SALES\nPHONE-MAIN\n"

    assert normalized_phone_numbers(value) == ["PHONE-MAIN", "PHONE-SALES"]
