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
            <td class="meta-colon">:</td>
            <td class="meta-label" dir="rtl">{label}</td>
        </tr>
    """


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
    company_ar, company_en = _company_parts(settings.get("company_name"))

    line_rows: list[str] = []
    for line in invoice.get("lines", []):
        line_rows.append(
            """
            <tr>
                <td class="money-cell" dir="ltr">{total}</td>
                <td class="money-cell" dir="ltr">{price}</td>
                <td class="qty-cell">
                    <div class="ltr-number" dir="ltr">{quantity:g}</div>
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
        f'<div class="logo-wrap"><img class="logo" width="105" src="{logo_url}"></div>'
        if logo_url
        else ""
    )

    qr_html = ""
    if qr_url:
        qr_html = f"""
        <div class="payment-block">
            <div class="payment-title">
                <span dir="rtl">الدفع عبر</span>
                <span dir="ltr">InstaPay</span>
            </div>
            <img class="qr" width="116" src="{qr_url}">
            <div class="handle" dir="ltr">{_text(settings.get('instapay_handle'))}</div>
            <div class="hint" dir="rtl">تأكد من اسم المستفيد قبل إتمام التحويل</div>
        </div>
        """

    footer = _text(settings.get("footer", "")).replace("\n", "<br>")
    customer_name = _text(invoice.get("customer_name", ""))
    customer_phone = _text(invoice.get("customer_phone", ""))
    invoice_number = _text(invoice.get("invoice_number"))
    order_number = _text(invoice.get("order_number"))
    invoice_date = _text(format_egypt_datetime(invoice.get("invoice_date")))
    invoice_total = _money(invoice.get("total"))
    invoice_paid = _money(invoice.get("paid"))
    invoice_remaining = _money(invoice.get("remaining"))
    payment_methods = _text(invoice.get("payment_methods") or "—")

    company_html = (
        f"""
        <table class="company-line" dir="ltr">
            <tr>
                <td class="company-en" dir="ltr">{_text(company_en)}</td>
                <td class="company-separator">-</td>
                <td class="company-ar" dir="rtl">{_text(company_ar)}</td>
            </tr>
        </table>
        """
        if company_en
        else f'<div class="company-single" dir="rtl">{_text(company_ar)}</div>'
    )

    meta_rows = [
        _meta_row("رقم الفاتورة", invoice_number),
        _meta_row("رقم الأمر", order_number),
        _meta_row("التاريخ", invoice_date),
        _meta_row("العميل", customer_name, rtl_value=True),
    ]
    if customer_phone:
        meta_rows.append(_meta_row("الهاتف", customer_phone))

    return f"""
    <!DOCTYPE html>
    <html lang="ar">
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                color: #000;
                background: #fff;
                font-family: "DejaVu Sans", "Tahoma", "Arial";
                font-size: 9pt;
                line-height: 1.18;
            }}
            .center {{ text-align: center; }}
            .logo-wrap {{ margin: 0 0 2pt; text-align: center; }}
            .logo {{ width: 105px; max-height: 74pt; }}

            .company-line {{
                width: 100%;
                border-collapse: collapse;
                margin: 1pt 0;
            }}
            .company-line td {{
                border: 0;
                padding: 0 1pt;
                white-space: nowrap;
                font-size: 10.5pt;
                font-weight: 900;
                vertical-align: middle;
            }}
            .company-en {{ width: 42%; text-align: right; font-family: "Arial", "DejaVu Sans"; }}
            .company-separator {{ width: 6%; text-align: center; }}
            .company-ar {{ width: 52%; text-align: left; }}
            .company-single {{ font-size: 10.5pt; font-weight: 900; text-align: center; }}
            .address {{ direction: rtl; text-align: center; font-size: 8.5pt; margin-top: 1pt; }}
            .phones {{ direction: ltr; text-align: center; font-family: "Arial", "DejaVu Sans"; font-size: 8.2pt; margin-top: 1pt; }}
            .invoice-title {{
                border-top: 2px solid #000;
                border-bottom: 2px solid #000;
                font-size: 11.5pt;
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
                table-layout: fixed;
            }}
            .meta td {{ padding: 1.5pt 0; vertical-align: middle; border: 0; }}
            .meta-value {{ width: 55%; }}
            .meta-colon {{ width: 5%; text-align: center; font-weight: 900; }}
            .meta-label {{ width: 40%; text-align: right; font-weight: 900; white-space: nowrap; }}
            .ltr-value {{ direction: ltr; text-align: left; font-family: "Arial", "DejaVu Sans"; }}
            .rtl-value {{ direction: rtl; text-align: left; }}

            .items {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                direction: ltr;
                border: 1.5px solid #000;
                page-break-inside: avoid;
            }}
            .items th, .items td {{
                border: 1px solid #000;
                padding: 3.5pt 1pt;
                vertical-align: middle;
            }}
            .items th {{
                font-size: 7.8pt;
                font-weight: 900;
                text-align: center;
                white-space: nowrap;
            }}
            .total-col {{ width: 22%; }}
            .price-col {{ width: 18%; }}
            .qty-col {{ width: 14%; }}
            .product-col {{ width: 46%; text-align: right !important; }}
            .money-cell {{
                direction: ltr;
                text-align: center;
                font-family: "Arial", "DejaVu Sans";
                font-size: 7.5pt;
                font-weight: 800;
                white-space: nowrap;
            }}
            .qty-cell {{ text-align: center; }}
            .ltr-number {{ direction: ltr; font-family: "Arial", "DejaVu Sans"; font-weight: 800; }}
            .unit {{ font-size: 7pt; margin-top: 1pt; }}
            .product-cell {{ direction: rtl; text-align: right; }}
            .product-name {{ font-size: 8pt; font-weight: 900; }}
            .product-code {{ direction: ltr; text-align: right; font-family: "Arial", "DejaVu Sans"; font-size: 7pt; margin-top: 1pt; }}

            .totals-wrap {{ text-align: center; margin-top: 6pt; }}
            .totals {{
                width: 76%;
                margin-left: auto;
                margin-right: auto;
                border-collapse: collapse;
                direction: ltr;
            }}
            .totals td {{ padding: 2pt 1pt; }}
            .totals .value {{
                width: 54%;
                direction: ltr;
                text-align: left;
                font-family: "Arial", "DejaVu Sans";
                font-size: 10pt;
                font-weight: 900;
                white-space: nowrap;
            }}
            .totals .colon {{ width: 6%; text-align: center; font-weight: 900; }}
            .totals .label {{ width: 40%; direction: rtl; text-align: right; font-size: 10pt; font-weight: 900; }}
            .totals .grand td {{ border-top: 2px solid #000; font-size: 11.5pt; }}
            .totals .remaining td {{ border-bottom: 1px dashed #000; }}
            .method-value {{ direction: rtl !important; text-align: left !important; font-family: "DejaVu Sans", "Tahoma" !important; font-size: 9pt !important; }}

            .payment-block {{ text-align: center; margin-top: 7pt; page-break-inside: avoid; }}
            .payment-title {{ font-size: 10pt; font-weight: 900; margin-bottom: 2pt; }}
            .payment-title span {{ margin: 0 1pt; }}
            .qr {{ width: 116px; }}
            .handle {{ direction: ltr; text-align: center; font-family: "Arial", "DejaVu Sans"; font-weight: 900; font-size: 8.8pt; margin-top: 1pt; }}
            .hint {{ direction: rtl; text-align: center; font-size: 7.2pt; margin-top: 2pt; }}
            .footer-divider {{ border-top: 1px dashed #000; margin-top: 5pt; }}
            .footer {{ direction: rtl; text-align: center; font-size: 8.5pt; font-weight: 800; margin-top: 4pt; }}
        </style>
    </head>
    <body>
        <div class="center">
            {logo_html}
            {company_html}
            <div class="address">{_text(settings.get('address'))}</div>
            <div class="phones">{_text(phones)}</div>
            <div class="invoice-title">فاتورة مبيعات</div>
        </div>

        <table class="meta" dir="ltr">
            {''.join(meta_rows)}
        </table>

        <table class="items" dir="ltr">
            <colgroup>
                <col style="width:22%">
                <col style="width:18%">
                <col style="width:14%">
                <col style="width:46%">
            </colgroup>
            <tr>
                <th class="total-col" dir="rtl">الإجمالي</th>
                <th class="price-col" dir="rtl">السعر</th>
                <th class="qty-col" dir="rtl">الكمية</th>
                <th class="product-col" dir="rtl">الصنف</th>
            </tr>
            {''.join(line_rows)}
        </table>

        <div class="totals-wrap">
            <table class="totals" dir="ltr">
                <tr class="grand"><td class="value" dir="ltr">{invoice_total}</td><td class="colon">:</td><td class="label" dir="rtl">الإجمالي</td></tr>
                <tr><td class="value" dir="ltr">{invoice_paid}</td><td class="colon">:</td><td class="label" dir="rtl">المدفوع</td></tr>
                <tr class="remaining"><td class="value" dir="ltr">{invoice_remaining}</td><td class="colon">:</td><td class="label" dir="rtl">المتبقي</td></tr>
                <tr><td class="value method-value" dir="rtl">{payment_methods}</td><td class="colon">:</td><td class="label" dir="rtl">طريقة الدفع</td></tr>
            </table>
        </div>

        {qr_html}
        <div class="footer-divider"></div>
        <div class="footer">{footer}</div>
    </body>
    </html>
    """
