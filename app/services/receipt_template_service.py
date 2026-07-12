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


def _date_parts(value: object) -> tuple[str, str]:
    formatted = format_egypt_datetime(value)
    if " " not in formatted:
        return formatted, ""
    date_value, time_value = formatted.split(" ", 1)
    return date_value, time_value


def _meta_row(label: str, value: str, *, rtl_value: bool = False) -> str:
    value_direction = "rtl" if rtl_value else "ltr"
    value_class = "meta-value rtl-value" if rtl_value else "meta-value ltr-value"
    return f"""
        <tr>
            <td class="meta-label" dir="rtl">{_text(label)}</td>
            <td class="{value_class}" dir="{value_direction}">{value}</td>
        </tr>
    """


def _line_row(line: dict) -> str:
    quantity = float(line.get("quantity", 0) or 0)
    return f"""
        <tr>
            <td class="product-cell" dir="rtl">
                <div class="product-name">{_text(line.get("name"))}</div>
                <div class="product-code" dir="ltr">{_text(line.get("code"))}</div>
            </td>
            <td class="qty-cell" dir="ltr">{quantity:g}</td>
            <td class="unit-cell" dir="rtl">{_text(line.get("unit"))}</td>
            <td class="money-cell" dir="ltr">{_money(line.get("unit_price"))}</td>
            <td class="money-cell" dir="ltr">{_money(line.get("line_total"))}</td>
        </tr>
    """


def build_sales_receipt_html(
    invoice: dict,
    settings: dict[str, str],
    *,
    logo_url: str = "",
    qr_url: str = "",
) -> str:
    company_ar, company_en = _company_parts(settings.get("company_name"))
    phones = [
        line.strip()
        for line in str(settings.get("phones", "")).splitlines()
        if line.strip()
    ]
    phones_html = "<br>".join(_text(phone) for phone in phones)

    invoice_date, invoice_time = _date_parts(invoice.get("invoice_date"))
    meta_rows = [
        _meta_row("رقم الفاتورة", _text(invoice.get("invoice_number"))),
        _meta_row("رقم أمر البيع", _text(invoice.get("order_number"))),
        _meta_row("التاريخ", _text(invoice_date)),
    ]
    if invoice_time:
        meta_rows.append(_meta_row("الوقت", _text(invoice_time)))
    meta_rows.append(
        _meta_row("اسم العميل", _text(invoice.get("customer_name")), rtl_value=True)
    )
    customer_phone = str(invoice.get("customer_phone", "") or "").strip()
    if customer_phone:
        meta_rows.append(_meta_row("رقم الهاتف", _text(customer_phone)))
    meta_rows.append(
        _meta_row(
            "طريقة الدفع",
            _text(invoice.get("payment_methods") or "—"),
            rtl_value=True,
        )
    )

    item_rows = "".join(_line_row(line) for line in invoice.get("lines", []))
    if not item_rows:
        item_rows = """
            <tr>
                <td class="empty-row" colspan="5" dir="rtl">لا توجد أصناف</td>
            </tr>
        """

    logo_html = ""
    if logo_url:
        logo_html = (
            f'<div class="logo-wrap"><img class="logo" width="132" '
            f'src="{logo_url}"></div>'
        )

    payment_html = ""
    instapay_handle = _text(settings.get("instapay_handle"))
    if qr_url or instapay_handle:
        qr_html = (
            f'<img class="qr" width="154" src="{qr_url}">'
            if qr_url
            else ""
        )
        handle_html = (
            f'<div class="instapay-handle" dir="ltr">{instapay_handle}</div>'
            if instapay_handle
            else ""
        )
        payment_html = f"""
            <div class="section-divider"></div>
            <div class="payment-block">
                <div class="payment-title" dir="rtl">الدفع عبر InstaPay</div>
                {qr_html}
                {handle_html}
            </div>
        """

    footer = _text(settings.get("footer", "")).replace("\n", "<br>")
    notes = str(invoice.get("notes", "") or "").strip()
    notes_html = ""
    if notes:
        notes_html = f"""
            <div class="notes" dir="rtl">
                <div class="notes-title">ملاحظات</div>
                <div>{_text(notes)}</div>
            </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                color: #000000;
                background: #ffffff;
                font-family: "DejaVu Sans", "Tahoma", "Arial";
                font-size: 8.8pt;
            }}
            .receipt {{
                width: 100%;
                margin: 0;
                padding: 0;
            }}
            .header {{
                width: 100%;
                text-align: center;
            }}
            .logo-wrap {{
                text-align: center;
                margin: 3pt 0 7pt 0;
            }}
            .logo {{
                width: 132px;
                max-height: 100pt;
            }}
            .company-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 2pt 0 0 0;
            }}
            .company-table td {{
                width: 50%;
                border: 0;
                padding: 0 2pt;
                font-size: 10.4pt;
                font-weight: 900;
                white-space: nowrap;
            }}
            .company-ar {{
                text-align: right;
                direction: rtl;
            }}
            .company-en {{
                text-align: left;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
            }}
            .address {{
                margin-top: 5pt;
                text-align: center;
                direction: rtl;
                font-size: 8.4pt;
                font-weight: 700;
            }}
            .phones {{
                margin-top: 4pt;
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8.4pt;
                font-weight: 800;
                line-height: 1.35;
            }}
            .invoice-title {{
                margin: 10pt 0 8pt 0;
                padding: 5pt 0;
                text-align: center;
                direction: rtl;
                border-top: 2px solid #000000;
                border-bottom: 2px solid #000000;
                font-size: 11pt;
                font-weight: 900;
            }}
            .meta {{
                width: 100%;
                border-collapse: collapse;
                margin: 2pt 0 10pt 0;
                direction: rtl;
            }}
            .meta td {{
                border: 0;
                padding: 2.8pt 1pt;
                vertical-align: top;
            }}
            .meta-label {{
                width: 40%;
                text-align: right;
                direction: rtl;
                font-weight: 900;
                white-space: nowrap;
            }}
            .meta-value {{
                width: 60%;
                text-align: right;
                font-weight: 700;
            }}
            .ltr-value {{
                direction: ltr;
                text-align: right;
                font-family: "Arial", "DejaVu Sans";
            }}
            .rtl-value {{
                direction: rtl;
                text-align: right;
            }}
            .items {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                border: 1px solid #000000;
                direction: rtl;
            }}
            .items th,
            .items td {{
                border: 1px solid #000000;
                padding: 5pt 1pt;
                vertical-align: middle;
            }}
            .items th {{
                background: #efefef;
                text-align: center;
                direction: rtl;
                font-size: 7.1pt;
                font-weight: 900;
            }}
            .product-head,
            .product-cell {{ width: 38%; }}
            .qty-head,
            .qty-cell {{ width: 12%; }}
            .unit-head,
            .unit-cell {{ width: 13%; }}
            .price-head {{ width: 18%; }}
            .total-head {{ width: 19%; }}
            .product-cell {{
                text-align: right;
                direction: rtl;
            }}
            .product-name {{
                font-size: 7.7pt;
                font-weight: 900;
                line-height: 1.35;
            }}
            .product-code {{
                margin-top: 2pt;
                text-align: right;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 6.7pt;
            }}
            .qty-cell,
            .unit-cell,
            .money-cell {{
                text-align: center;
                font-size: 7.2pt;
                font-weight: 800;
            }}
            .money-cell {{
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                white-space: nowrap;
            }}
            .empty-row {{
                text-align: center;
                padding: 12pt 0;
            }}
            .totals-wrap {{
                width: 86%;
                margin: 11pt auto 0 auto;
                border-collapse: collapse;
                direction: rtl;
            }}
            .totals-wrap td {{
                padding: 4.5pt 4pt;
                border-bottom: 1px solid #000000;
                font-size: 9.4pt;
                font-weight: 900;
            }}
            .totals-label {{
                width: 47%;
                text-align: right;
                direction: rtl;
            }}
            .totals-value {{
                width: 53%;
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
            }}
            .remaining-row td {{
                border-top: 2px solid #000000;
                border-bottom: 2px solid #000000;
                font-size: 10.4pt;
            }}
            .notes {{
                margin-top: 10pt;
                padding: 5pt;
                border: 1px solid #000000;
                text-align: right;
                direction: rtl;
                font-size: 8pt;
            }}
            .notes-title {{
                margin-bottom: 3pt;
                font-weight: 900;
            }}
            .section-divider {{
                margin-top: 12pt;
                border-top: 1px dashed #000000;
            }}
            .payment-block {{
                margin-top: 8pt;
                text-align: center;
            }}
            .payment-title {{
                margin-bottom: 6pt;
                font-size: 9.8pt;
                font-weight: 900;
            }}
            .qr {{
                width: 154px;
                max-height: 190pt;
            }}
            .instapay-handle {{
                margin-top: 5pt;
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8.6pt;
                font-weight: 900;
            }}
            .footer-divider {{
                margin-top: 12pt;
                border-top: 1px dashed #000000;
            }}
            .footer {{
                margin-top: 7pt;
                text-align: center;
                direction: rtl;
                font-size: 8.2pt;
                font-weight: 800;
                line-height: 1.4;
            }}
            .bottom-space {{
                height: 8pt;
            }}
        </style>
    </head>
    <body>
        <div class="receipt">
            <div class="header">
                {logo_html}
                <table class="company-table" cellspacing="0" cellpadding="0">
                    <tr>
                        <td class="company-ar" dir="rtl">{_text(company_ar)}</td>
                        <td class="company-en" dir="ltr">{_text(company_en)}</td>
                    </tr>
                </table>
                <div class="address">{_text(settings.get("address"))}</div>
                <div class="phones">{phones_html}</div>
                <div class="invoice-title">فاتورة مبيعات</div>
            </div>

            <table class="meta" cellspacing="0" cellpadding="0">
                {"".join(meta_rows)}
            </table>

            <table class="items" cellspacing="0" cellpadding="0">
                <tr>
                    <th class="product-head">الصنف</th>
                    <th class="qty-head">الكمية</th>
                    <th class="unit-head">الوحدة</th>
                    <th class="price-head">سعر الوحدة</th>
                    <th class="total-head">الإجمالي</th>
                </tr>
                {item_rows}
            </table>

            <table class="totals-wrap" cellspacing="0" cellpadding="0">
                <tr>
                    <td class="totals-label">الإجمالي</td>
                    <td class="totals-value">{_money(invoice.get("total"))}</td>
                </tr>
                <tr>
                    <td class="totals-label">المدفوع</td>
                    <td class="totals-value">{_money(invoice.get("paid"))}</td>
                </tr>
                <tr class="remaining-row">
                    <td class="totals-label">المتبقي</td>
                    <td class="totals-value">{_money(invoice.get("remaining"))}</td>
                </tr>
            </table>

            {notes_html}
            {payment_html}

            <div class="footer-divider"></div>
            <div class="footer">{footer}</div>
            <div class="bottom-space"></div>
        </div>
    </body>
    </html>
    """


__all__ = ["build_sales_receipt_html"]
