from app.services.receipt_template_service import build_sales_receipt_html


def _invoice() -> dict:
    return {
        "invoice_number": "SI00001",
        "order_number": "SO00001",
        "invoice_date": "2026-07-12T14:50:12+00:00",
        "customer_name": "يوسف حجاج",
        "customer_phone": "PHONE-TEST-CUSTOMER",
        "payment_methods": "تحويل بنكي",
        "total": 100000,
        "paid": 100000,
        "remaining": 0,
        "notes": "",
        "lines": [
            {
                "name": "مواسير صرف محسن",
                "code": "1001",
                "quantity": 100,
                "unit": "قطعة",
                "unit_price": 1000,
                "line_total": 100000,
            }
        ],
    }


def _settings() -> dict[str, str]:
    return {
        "company_name": "ثري ايه بايب - 3A PIPES",
        "address": "المنوفية - سرس الليان",
        "phones": "PHONE-TEST-1\nPHONE-TEST-2",
        "instapay_handle": "receipt-test@example.invalid",
        "footer": (
            "اسم المستفيد: ثري ايه بايب - 3A Pipes\n"
            "تأكد من اسم المستفيد قبل إتمام التحويل\n"
            "شكراً لثقتكم في ثري ايه بايب"
        ),
    }


def test_receipt_template_uses_five_proportional_columns_and_right_meta() -> None:
    html = build_sales_receipt_html(_invoice(), _settings())

    assert '<th width="34%">الصنف</th>' in html
    assert '<th width="11%">كمية</th>' in html
    assert '<th width="11%">وحدة</th>' in html
    assert '<th width="20%">السعر</th>' in html
    assert '<th width="24%">الإجمالي</th>' in html
    assert 'class="qty-cell" width="11%"' in html
    assert 'class="unit-cell" width="11%"' in html
    assert "سعر الوحدة" not in html
    assert 'class="meta-label" width="43%" dir="rtl">رقم الفاتورة:</td>' in html
    assert html.index('<th width="24%">الإجمالي</th>') < html.index('<th width="34%">الصنف</th>')
    invoice_row = html[html.index("SI00001") :]
    assert invoice_row.index("SI00001") < invoice_row.index("رقم الفاتورة:")
    first_item_row = html[html.index('class="money-cell total-cell"') :]
    assert first_item_row.index('class="money-cell total-cell"') < first_item_row.index(
        'class="product-cell"'
    )
    assert "table-layout" not in html
    assert "max-height" not in html


def test_receipt_removes_only_the_obsolete_beneficiary_line() -> None:
    html = build_sales_receipt_html(_invoice(), _settings())

    assert "اسم المستفيد: ثري ايه بايب" not in html
    assert "تأكد من اسم المستفيد قبل إتمام التحويل" in html
    assert "شكراً لثقتكم" in html
