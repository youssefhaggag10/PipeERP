from html import escape

from app.utils.datetime_utils import format_egypt_datetime


def _text(value: object) -> str:
    return escape(str(value or ""))


def _money(value: object) -> str:
    return f"{float(value or 0):,.2f}"


def _company_name_html(value: object) -> str:
    """Render Arabic and English company names on one stable bilingual line."""
    text = str(value or "").strip()
    if not text:
        return ""

    for separator in (" - ", " – ", " — "):
        if separator in text:
            arabic, english = text.split(separator, 1)
            return (
                f'<span class="company-ar" dir="rtl">{_text(arabic.strip())}</span>'
                '<span class="company-separator"> - </span>'
                f'<span class="company-en" dir="ltr">{_text(english.strip().upper())}</span>'
            )
    return f'<span dir="auto">{_text(text)}</span>'


def build_sales_receipt_html(
    invoice: dict,
    settings: dict[str, str],
    *,
    logo_url: str = "",
    qr_url: str = "",
) -> str:
    phones = " | ".join(
        line.strip() for line in settings.get("phones", "").splitlines() if line.strip()
    )
    customer_name = _text(invoice.get("customer_name", ""))
    customer_phone = _text(invoice.get("customer_phone", ""))
    customer_html = f'<div class="rtl-value">{customer_name}</div>'
    if customer_phone:
        customer_html += f'<div class="ltr-value customer-phone">{customer_phone}</div>'

    line_rows = []
    for index, line in enumerate(invoice.get("lines", []), start=1):
        line_rows.append(
            """
            <tr>
                <td class="product-cell">
                    <div class="product-name">{index}. {name}</div>
                    <div class="product-code" dir="ltr">{code}</div>
                </td>
                <td class="quantity-cell">
                    <div class="number" dir="ltr">{quantity:g}</div>
                    <div class="unit">{unit}</div>
                </td>
                <td class="number-cell" dir="ltr">{price}</td>
                <td class="number-cell line-total" dir="ltr">{total}</td>
            </tr>
            """.format(
                index=index,
                name=_text(line.get("name")),
                code=_text(line.get("code")),
                quantity=float(line.get("quantity", 0)),
                unit=_text(line.get("unit")),
                price=_money(line.get("unit_price")),
                total=_money(line.get("line_total")),
            )
        )

    logo_html = (
        f'<div class="logo-wrap"><img class="logo" width="112" src="{logo_url}"></div>'
        if logo_url
        else ""
    )
    qr_html = ""
    if qr_url:
        qr_html = f"""
        <div class="payment">
            <div class="payment-title">الدفع عبر InstaPay</div>
            <img class="qr" width="116" src="{qr_url}">
            <div class="beneficiary" dir="rtl">
                <strong>اسم المستفيد:</strong>
                {_text(settings.get('beneficiary_name'))}
            </div>
            <div class="handle" dir="ltr">{_text(settings.get('instapay_handle'))}</div>
            <div class="hint">تأكد من اسم المستفيد قبل إتمام التحويل</div>
        </div>
        """

    payment_methods = _text(invoice.get("payment_methods") or "—")
    footer = _text(settings.get("footer", "")).replace("\n", "<br>")
    invoice_number = _text(invoice.get("invoice_number"))
    order_number = _text(invoice.get("order_number"))
    invoice_date = _text(format_egypt_datetime(invoice.get("invoice_date")))
    invoice_total = _money(invoice.get("total"))
    invoice_paid = _money(invoice.get("paid"))
    invoice_remaining = _money(invoice.get("remaining"))
    company_name = _company_name_html(settings.get("company_name"))

    return f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                direction: rtl;
                font-family: "DejaVu Sans", "Tahoma", "Arial";
                color: #000;
                background: #fff;
                font-size: 9.5pt;
                line-height: 1.22;
                margin: 0;
            }}
            .center {{ text-align: center; }}
            .logo-wrap {{ height: 76pt; margin: 0 0 1pt; text-align: center; }}
            .logo {{ width: 112px; }}
            .company {{
                direction: rtl;
                white-space: nowrap;
                font-size: 11.5pt;
                font-weight: 800;
                margin: 1pt 0;
                text-align: center;
            }}
            .company-ar {{ font-family: "DejaVu Sans", "Tahoma"; }}
            .company-en {{ font-family: "Arial", "DejaVu Sans"; font-weight: 900; }}
            .company-separator {{ padding: 0 1pt; }}
            .address {{ direction: rtl; font-size: 8.8pt; margin-top: 1pt; }}
            .phones {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8.5pt;
                margin-top: 1pt;
            }}
            .invoice-title {{
                border-top: 2px solid #000;
                border-bottom: 2px solid #000;
                font-size: 12pt;
                font-weight: 900;
                margin: 5pt 0 3pt;
                padding: 3pt 0;
                text-align: center;
            }}
            .section-gap {{ height: 2pt; }}
            .meta, .totals, .items {{ width: 100%; border-collapse: collapse; }}
            .meta {{ direction: rtl; margin-bottom: 3pt; }}
            .meta td {{ padding: 1.8pt 1pt; vertical-align: top; }}
            .meta-label {{
                width: 34%;
                direction: rtl;
                text-align: right;
                font-weight: 800;
                white-space: nowrap;
            }}
            .meta-value {{ width: 66%; text-align: left; }}
            .rtl-value {{ direction: rtl; text-align: right; }}
            .ltr-value {{ direction: ltr; text-align: left; font-family: "Arial", "DejaVu Sans"; }}
            .customer-phone {{ font-size: 8.5pt; margin-top: 1pt; }}
            .items {{ direction: rtl; table-layout: fixed; margin-top: 2pt; }}
            .items th {{
                border-top: 2px solid #000;
                border-bottom: 2px solid #000;
                padding: 3pt 1pt;
                font-size: 8.5pt;
                font-weight: 900;
                text-align: center;
                white-space: nowrap;
            }}
            .items td {{
                border-bottom: 1px solid #000;
                padding: 4pt 1pt;
                vertical-align: top;
            }}
            .product-head {{ width: 44%; text-align: right !important; }}
            .quantity-head {{ width: 15%; }}
            .price-head {{ width: 18%; }}
            .total-head {{ width: 23%; }}
            .product-cell {{ width: 44%; direction: rtl; text-align: right; }}
            .product-name {{ font-weight: 700; }}
            .product-code {{
                direction: ltr;
                text-align: right;
                font-family: "Arial", "DejaVu Sans";
                font-size: 7.3pt;
                margin-top: 1pt;
            }}
            .quantity-cell {{ width: 15%; text-align: center; }}
            .number {{ direction: ltr; font-family: "Arial", "DejaVu Sans"; white-space: nowrap; }}
            .unit {{ direction: rtl; font-size: 7.5pt; margin-top: 1pt; }}
            .number-cell {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8pt;
                white-space: nowrap;
            }}
            .line-total {{ font-weight: 800; }}
            .totals {{ direction: rtl; margin-top: 4pt; }}
            .totals td {{ padding: 2.4pt 1pt; font-size: 10pt; }}
            .totals .total-label {{ direction: rtl; text-align: right; font-weight: 700; }}
            .totals .value {{
                direction: ltr;
                text-align: left;
                font-family: "Arial", "DejaVu Sans";
                font-weight: 800;
                white-space: nowrap;
            }}
            .grand td {{ border-top: 2px solid #000; font-size: 12pt; font-weight: 900; }}
            .remaining td {{ border-bottom: 1px dashed #000; font-weight: 900; }}
            .payment {{ text-align: center; margin-top: 7pt; }}
            .payment-title {{ font-size: 10.5pt; font-weight: 900; margin-bottom: 2pt; }}
            .qr {{ width: 116px; }}
            .beneficiary {{ font-size: 8.5pt; margin-top: 2pt; }}
            .handle {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-weight: 900;
                font-size: 9pt;
                margin-top: 1pt;
            }}
            .hint {{ font-size: 7.5pt; margin-top: 2pt; }}
            .footer-divider {{ border-top: 1px dashed #000; margin-top: 5pt; }}
            .footer {{ direction: rtl; text-align: center; font-size: 8.8pt; font-weight: 800; margin-top: 4pt; }}
        </style>
    </head>
    <body>
        <div class="center">
            {logo_html}
            <div class="company">{company_name}</div>
            <div class="address">{_text(settings.get('address'))}</div>
            <div class="phones">{_text(phones)}</div>
            <div class="invoice-title">فاتورة مبيعات</div>
        </div>

        <table class="meta" dir="rtl">
            <tr>
                <td class="meta-label">رقم الفاتورة:</td>
                <td class="meta-value ltr-value">{invoice_number}</td>
            </tr>
            <tr>
                <td class="meta-label">رقم الأمر:</td>
                <td class="meta-value ltr-value">{order_number}</td>
            </tr>
            <tr>
                <td class="meta-label">التاريخ:</td>
                <td class="meta-value ltr-value">{invoice_date}</td>
            </tr>
            <tr>
                <td class="meta-label">العميل:</td>
                <td class="meta-value">{customer_html}</td>
            </tr>
        </table>

        <table class="items" dir="rtl">
            <colgroup>
                <col style="width:44%">
                <col style="width:15%">
                <col style="width:18%">
                <col style="width:23%">
            </colgroup>
            <thead>
                <tr>
                    <th class="product-head">الصنف</th>
                    <th class="quantity-head">الكمية</th>
                    <th class="price-head">السعر</th>
                    <th class="total-head">الإجمالي</th>
                </tr>
            </thead>
            <tbody>{''.join(line_rows)}</tbody>
        </table>

        <table class="totals" dir="rtl">
            <tr class="grand"><td class="total-label">الإجمالي</td><td class="value">{invoice_total}</td></tr>
            <tr><td class="total-label">المدفوع</td><td class="value">{invoice_paid}</td></tr>
            <tr class="remaining"><td class="total-label">المتبقي</td><td class="value">{invoice_remaining}</td></tr>
            <tr><td class="total-label">طريقة الدفع</td><td class="value">{payment_methods}</td></tr>
        </table>

        {qr_html}
        <div class="footer-divider"></div>
        <div class="footer">{footer}</div>
    </body>
    </html>
    """
