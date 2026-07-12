from app.services.a4_invoice_template_service import build_sales_invoice_a4_html


def _invoice() -> dict:
    return {
        "invoice_number": "SI-TEST-001",
        "order_number": "SO-TEST-001",
        "invoice_date": "2026-07-12T14:50:12+00:00",
        "customer_name": "عميل تجريبي",
        "customer_phone": "PHONE-TEST-CUSTOMER",
        "payment_methods": "تحويل بنكي",
        "total": 100000,
        "paid": 75000,
        "remaining": 25000,
        "notes": "مدة التوريد طبقًا للاتفاق.",
        "lines": [
            {
                "name": "ماسورة اختبار",
                "code": "ITEM-001",
                "quantity": 100,
                "unit": "قطعة",
                "unit_price": 1000,
                "line_total": 100000,
            }
        ],
    }


def _settings() -> dict[str, str]:
    return {
        "company_name": "شركة تجريبية - TEST COMPANY",
        "address": "عنوان تجريبي",
        "phones": "PHONE-TEST-1\nPHONE-TEST-2",
        "instapay_handle": "invoice-test@example.invalid",
        "footer": "شكرًا لتعاملكم معنا.",
    }


def test_a4_invoice_has_company_layout_and_sales_title() -> None:
    html = build_sales_invoice_a4_html(
        _invoice(),
        _settings(),
        logo_url="invoice:logo",
        qr_url="invoice:instapay-qr",
    )

    assert "فاتورة مبيعات" in html
    assert "طلب عرض سعر" not in html
    assert "background-color: #2f69a5" in html
    assert "background-color: #f5cc25" in html
    assert 'src="invoice:logo"' in html
    assert 'src="invoice:instapay-qr"' in html


def test_a4_invoice_columns_render_product_on_the_right() -> None:
    html = build_sales_invoice_a4_html(_invoice(), _settings())

    total_header = html.index('<th width="15%">الإجمالي</th>')
    description_header = html.index('<th width="33%">البيان</th>')
    serial_header = html.index('<th width="5%">م</th>')
    assert total_header < description_header < serial_header
    assert '<th width="9%">الكمية</th>' in html
    assert '<th width="10%">الوحدة</th>' in html
    assert 'class="description-cell" width="33%"' in html


def test_a4_invoice_contains_customer_totals_and_payment_data() -> None:
    html = build_sales_invoice_a4_html(_invoice(), _settings())

    assert "SI-TEST-001" in html
    assert "عميل تجريبي" in html
    assert "100,000.00 جنيه" in html
    assert "75,000.00 جنيه" in html
    assert "25,000.00 جنيه" in html
    assert "invoice-test@example.invalid" in html
