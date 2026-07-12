from html import escape

from app.utils.datetime_utils import format_egypt_datetime


def _text(value: object) -> str:
    return escape(str(value or ""))


def _money(value: object) -> str:
    return f"{float(value or 0):,.2f}"


def _company_parts(value: object) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    for separator in (" - ", " – ", " — "):
        if separator in text:
            arabic, english = text.split(separator, 1)
            return arabic.strip(), english.strip().upper()
    return text, ""


def _meta_row(label: str, value: str, *, rtl_value: bool = False) -> str:
    value_class = "meta-value rtl-value" if rtl_value else "meta-value ltr-value"
    value_dir = "rtl" if rtl_value else "ltr"
    return f"""
        <tr>
            <td class="{value_class}" dir="{value_dir}">{value}</td>
            <td class="meta-label" dir="rtl">{label}</td>
        </tr>
    """


def _date_parts(value: object) -> tuple[str, str]:
    formatted = format_egypt_datetime(value)
    if " " not in formatted:
        return formatted, ""
    date, time = formatted.split(" ", 1)
    return date, time


def build_sales_receipt_html(
    invoice: dict,
    settings: dict[str, str],
    *,
    logo_url: str = "",
    qr_url: str = "",
) -> str:
    """Build a Qt-rich-text-safe 80 mm sales receipt.

    QTextDocument supports only a subset of browser CSS. In particular, nested percentage
    widths and auto margins can collapse columns on thermal printers. The receipt therefore
    uses full-width tables and explicit cell widths for predictable Arabic/RTL rendering.
    """
    phones = " | ".join(
        line.strip() for line in settings.get("phones", "").splitlines() if line.strip()
    )
    company_ar, company_en = _company_parts(settings.get("company_name"))

    line_rows: list[str] = []
    for line in invoice.get("lines", []):
        line_rows.append(
            """
            <tr>
                <td class="money-cell" dir="ltr">{total}</td>
                <td class="money-cell" dir="ltr">{price}</td>
                <td class="qty-cell" dir="ltr">
                    <div class="quantity">{quantity:g}</div>
                    <div class="unit" dir="rtl">{unit}</div>
                </td>
                <td class="product-cell" dir="rtl">
                    <div class="product-name">{name}</div>
                    <div class="product-code" dir="ltr">{code}</div>
                </td>
            </tr>
            """.format(
                name=_text(line.get("name")),
                code=_text(line.get("code")),
                quantity=float(line.get("quantity", 0)),
                unit=_text(line.get("unit")),
                price=_money(line.get("unit_price")),
                total=_money(line.get("line_total")),
            )
        )

    logo_html = (
        f'<div class="logo-wrap"><img class="logo" width="88" src="{logo_url}"></div>'
        if logo_url
        else ""
    )

    instapay_handle = _text(settings.get("instapay_handle"))
    qr_html = ""
    if qr_url:
        qr_html = f"""
        <div class="payment-block">
            <div class="payment-title" dir="rtl">الدفع عبر <span dir="ltr">InstaPay</span></div>
            <img class="qr" width="104" src="{qr_url}">
            <div class="handle" dir="ltr">{instapay_handle}</div>
            <div class="hint" dir="rtl">تأكد من اسم المستفيد قبل إتمام التحويل</div>
        </div>
        """
    elif instapay_handle:
        qr_html = f"""
        <div class="payment-block">
            <div class="payment-title" dir="rtl">الدفع عبر <span dir="ltr">InstaPay</span></div>
            <div class="handle" dir="ltr">{instapay_handle}</div>
        </div>
        """

    footer = _text(settings.get("footer", "")).replace("\n", "<br>")
    customer_name = _text(invoice.get("customer_name", ""))
    customer_phone = _text(invoice.get("customer_phone", ""))
    invoice_number = _text(invoice.get("invoice_number"))
    order_number = _text(invoice.get("order_number"))
    invoice_date, invoice_time = _date_parts(invoice.get("invoice_date"))
    invoice_total = _money(invoice.get("total"))
    invoice_paid = _money(invoice.get("paid"))
    invoice_remaining = _money(invoice.get("remaining"))
    payment_methods = _text(invoice.get("payment_methods") or "—")

    company_html = f"""
        <div class="company-ar" dir="rtl">{_text(company_ar)}</div>
        <div class="company-en" dir="ltr">{_text(company_en)}</div>
    """

    meta_rows = [
        _meta_row("رقم الفاتورة", invoice_number),
        _meta_row("رقم الأمر", order_number),
        _meta_row("التاريخ", _text(invoice_date)),
    ]
    if invoice_time:
        meta_rows.append(_meta_row("الوقت", _text(invoice_time)))
    meta_rows.append(_meta_row("العميل", customer_name, rtl_value=True))
    if customer_phone:
        meta_rows.append(_meta_row("الهاتف", customer_phone))

    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                color: #000;
                background: #fff;
                font-family: "DejaVu Sans", "Tahoma", "Arial";
                font-size: 8.6pt;
            }}
            .header {{ text-align: center; }}
            .logo-wrap {{ margin: 0 0 2pt; text-align: center; }}
            .logo {{ width: 88px; max-height: 58pt; }}
            .company-ar {{ font-size: 11pt; font-weight: 900; text-align: center; }}
            .company-en {{
                margin-top: 1pt;
                font-family: "Arial", "DejaVu Sans";
                font-size: 9.3pt;
                font-weight: 900;
                text-align: center;
            }}
            .address {{ direction: rtl; text-align: center; font-size: 8pt; margin-top: 2pt; }}
            .phones {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8pt;
                margin-top: 1pt;
            }}
            .invoice-title {{
                border-top: 2px solid #000;
                border-bottom: 2px solid #000;
                font-size: 11pt;
                font-weight: 900;
                margin: 5pt 0 4pt;
                padding: 3pt 0;
                text-align: center;
                direction: rtl;
            }}

            .meta {{
                width: 100%;
                border-collapse: collapse;
                direction: ltr;
                margin: 0 0 5pt;
            }}
            .meta td {{ padding: 1.4pt 2pt; vertical-align: middle; border: 0; }}
            .meta-value {{ width: 65%; font-weight: 700; }}
            .meta-label {{ width: 35%; text-align: right; font-weight: 900; white-space: nowrap; }}
            .ltr-value {{ direction: ltr; text-align: left; font-family: "Arial", "DejaVu Sans"; }}
            .rtl-value {{ direction: rtl; text-align: left; }}

            .items {{
                width: 100%;
                border-collapse: collapse;
                direction: ltr;
                border: 1px solid #000;
                page-break-inside: avoid;
            }}
            .items th, .items td {{
                border: 1px solid #000;
                padding: 3pt 1pt;
                vertical-align: middle;
            }}
            .items th {{
                background: #eeeeee;
                font-size: 7.4pt;
                font-weight: 900;
                text-align: center;
                white-space: nowrap;
            }}
            .total-head, .total-cell {{ width: 25%; }}
            .price-head, .price-cell {{ width: 21%; }}
            .qty-head, .qty-cell {{ width: 14%; }}
            .product-head, .product-cell {{ width: 40%; }}
            .money-cell {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-size: 7.3pt;
                font-weight: 800;
                white-space: nowrap;
            }}
            .qty-cell {{ text-align: center; }}
            .quantity {{ font-family: "Arial", "DejaVu Sans"; font-weight: 800; }}
            .unit {{ font-size: 6.8pt; margin-top: 1pt; }}
            .product-cell {{ direction: rtl; text-align: right; }}
            .product-name {{ font-size: 7.8pt; font-weight: 900; }}
            .product-code {{
                direction: ltr;
                text-align: right;
                font-family: "Arial", "DejaVu Sans";
                font-size: 6.8pt;
                margin-top: 1pt;
            }}

            .totals {{
                width: 100%;
                border-collapse: collapse;
                direction: ltr;
                margin-top: 5pt;
                page-break-inside: avoid;
            }}
            .totals td {{ padding: 2.4pt 3pt; border-bottom: 1px solid #d0d0d0; }}
            .totals .value {{
                width: 65%;
                direction: ltr;
                text-align: left;
                font-family: "Arial", "DejaVu Sans";
                font-size: 9.5pt;
                font-weight: 900;
            }}
            .totals .label {{
                width: 35%;
                direction: rtl;
                text-align: right;
                font-size: 9.5pt;
                font-weight: 900;
                white-space: nowrap;
            }}
            .totals .grand td {{
                border-top: 2px solid #000;
                border-bottom: 2px solid #000;
                font-size: 11pt;
            }}
            .totals .remaining td {{ border-bottom: 2px solid #000; }}
            .totals .method-value {{
                direction: rtl;
                text-align: left;
                font-family: "DejaVu Sans", "Tahoma";
                font-size: 8.8pt;
            }}

            .payment-block {{ text-align: center; margin-top: 7pt; page-break-inside: avoid; }}
            .payment-title {{ font-size: 9.5pt; font-weight: 900; margin-bottom: 2pt; }}
            .qr {{ width: 104px; }}
            .handle {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-weight: 900;
                font-size: 8.2pt;
                margin-top: 1pt;
            }}
            .hint {{ direction: rtl; text-align: center; font-size: 7pt; margin-top: 2pt; }}
            .footer-divider {{ border-top: 1px dashed #000; margin-top: 6pt; }}
            .footer {{
                direction: rtl;
                text-align: center;
                font-size: 8pt;
                font-weight: 800;
                margin-top: 4pt;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            {logo_html}
            {company_html}
            <div class="address">{_text(settings.get('address'))}</div>
            <div class="phones">{_text(phones)}</div>
            <div class="invoice-title">فاتورة مبيعات</div>
        </div>

        <table class="meta" width="100%" dir="ltr">
            {''.join(meta_rows)}
        </table>

        <table class="items" width="100%" dir="ltr" cellspacing="0" cellpadding="0">
            <tr>
                <th class="total-head" width="25%" dir="rtl">الإجمالي</th>
                <th class="price-head" width="21%" dir="rtl">السعر</th>
                <th class="qty-head" width="14%" dir="rtl">الكمية</th>
                <th class="product-head" width="40%" dir="rtl">الصنف</th>
            </tr>
            {''.join(line_rows)}
        </table>

        <table class="totals" width="100%" dir="ltr" cellspacing="0" cellpadding="0">
            <tr class="grand">
                <td class="value" dir="ltr">{invoice_total}</td>
                <td class="label" dir="rtl">الإجمالي</td>
            </tr>
            <tr>
                <td class="value" dir="ltr">{invoice_paid}</td>
                <td class="label" dir="rtl">المدفوع</td>
            </tr>
            <tr class="remaining">
                <td class="value" dir="ltr">{invoice_remaining}</td>
                <td class="label" dir="rtl">المتبقي</td>
            </tr>
            <tr>
                <td class="value method-value" dir="rtl">{payment_methods}</td>
                <td class="label" dir="rtl">طريقة الدفع</td>
            </tr>
        </table>

        {qr_html}
        <div class="footer-divider"></div>
        <div class="footer">{footer}</div>
    </body>
    </html>
    """
