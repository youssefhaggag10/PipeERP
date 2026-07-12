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
            <td class="meta-label" width="43%" dir="rtl">{_text(label)}:</td>
            <td class="{value_class}" width="57%" dir="{value_direction}">{value}</td>
        </tr>
    """


def _line_row(line: dict) -> str:
    quantity = float(line.get("quantity", 0) or 0)
    return f"""
        <tr>
            <td class="product-cell" width="42%" dir="rtl">
                <div class="product-name">{_text(line.get("name"))}</div>
                <div class="product-code" dir="ltr">{_text(line.get("code"))}</div>
            </td>
            <td class="qty-cell" width="16%" dir="rtl">
                <div dir="ltr">{quantity:g}</div>
                <div>{_text(line.get("unit"))}</div>
            </td>
            <td class="money-cell" width="19%" dir="ltr">{_money(line.get("unit_price"))}</td>
            <td class="money-cell" width="23%" dir="ltr">{_money(line.get("line_total"))}</td>
        </tr>
    """


def _clean_footer(value: object) -> str:
    """Drop the obsolete beneficiary row while preserving the configured note."""
    lines = []
    for line in str(value or "").splitlines():
        normalized = line.replace("ـ", "").strip()
        if normalized.startswith("اسم المستفيد:"):
            continue
        lines.append(line.strip())
    return "<br>".join(_text(line) for line in lines if line)


def build_sales_receipt_html(
    invoice: dict,
    settings: dict[str, str],
    *,
    logo_url: str = "",
    qr_url: str = "",
) -> str:
    company_ar, company_en = _company_parts(settings.get("company_name"))
    phones = [line.strip() for line in str(settings.get("phones", "")).splitlines() if line.strip()]
    phones_html = "<br>".join(_text(phone) for phone in phones)

    invoice_date, invoice_time = _date_parts(invoice.get("invoice_date"))
    meta_rows = [
        _meta_row("رقم الفاتورة", _text(invoice.get("invoice_number"))),
        _meta_row("رقم أمر البيع", _text(invoice.get("order_number"))),
        _meta_row("التاريخ", _text(invoice_date)),
    ]
    if invoice_time:
        meta_rows.append(_meta_row("الوقت", _text(invoice_time)))
    meta_rows.append(_meta_row("العميل", _text(invoice.get("customer_name")), rtl_value=True))
    customer_phone = str(invoice.get("customer_phone", "") or "").strip()
    if customer_phone:
        meta_rows.append(_meta_row("الهاتف", _text(customer_phone)))

    item_rows = "".join(_line_row(line) for line in invoice.get("lines", []))
    if not item_rows:
        item_rows = """
            <tr>
                <td class="empty-row" colspan="4" dir="rtl">لا توجد أصناف</td>
            </tr>
        """

    logo_html = ""
    if logo_url:
        logo_html = f'<div class="logo-wrap"><img width="116" src="{logo_url}"></div>'

    payment_method = _text(invoice.get("payment_methods") or "—")
    instapay_handle = _text(settings.get("instapay_handle"))
    payment_html = ""
    if qr_url or instapay_handle:
        qr_html = f'<img width="136" src="{qr_url}">' if qr_url else ""
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

    footer = _clean_footer(settings.get("footer", ""))
    footer_html = ""
    if footer:
        footer_html = f"""
            <div class="footer-divider"></div>
            <div class="footer">{footer}</div>
        """

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
                font-size: 8.2pt;
            }}
            .receipt {{ width: 100%; margin: 0; padding: 0; }}
            .header {{ width: 100%; text-align: center; }}
            .logo-wrap {{ text-align: center; margin: 3pt 0 6pt 0; }}
            .company-ar {{
                margin-top: 2pt;
                text-align: center;
                direction: rtl;
                font-size: 10.2pt;
                font-weight: 900;
            }}
            .company-en {{
                margin-top: 1pt;
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 9.8pt;
                font-weight: 900;
            }}
            .address {{
                margin-top: 5pt;
                text-align: center;
                direction: rtl;
                font-size: 8pt;
                font-weight: 700;
            }}
            .phones {{
                margin-top: 3pt;
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8pt;
                font-weight: 800;
            }}
            .invoice-title {{
                margin: 8pt 0 6pt 0;
                padding: 4pt 0;
                text-align: center;
                direction: rtl;
                border-top: 1px solid #000000;
                border-bottom: 1px solid #000000;
                font-size: 10.5pt;
                font-weight: 900;
            }}
            .meta {{
                width: 100%;
                border-collapse: collapse;
                margin: 1pt 0 8pt 0;
                direction: rtl;
            }}
            .meta td {{ border: 0; padding: 2.2pt 1pt; vertical-align: top; }}
            .meta-label {{
                text-align: right;
                direction: rtl;
                font-weight: 900;
                white-space: nowrap;
            }}
            .meta-value {{ text-align: right; font-weight: 750; }}
            .ltr-value {{
                direction: ltr;
                text-align: right;
                font-family: "Arial", "DejaVu Sans";
            }}
            .rtl-value {{ direction: rtl; text-align: right; }}
            .items {{
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #000000;
                direction: rtl;
            }}
            .items th, .items td {{
                border: 1px solid #000000;
                padding: 4pt 1pt;
                vertical-align: middle;
            }}
            .items th {{
                background: #efefef;
                text-align: center;
                direction: rtl;
                font-size: 6.9pt;
                font-weight: 900;
            }}
            .product-cell {{ text-align: right; direction: rtl; }}
            .product-name {{ font-size: 7.4pt; font-weight: 900; }}
            .product-code {{
                margin-top: 2pt;
                text-align: right;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 6.5pt;
            }}
            .qty-cell, .money-cell {{
                text-align: center;
                font-size: 6.9pt;
                font-weight: 800;
            }}
            .money-cell {{
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                white-space: nowrap;
            }}
            .empty-row {{ text-align: center; padding: 10pt 0; }}
            .totals-wrap {{
                width: 88%;
                margin-top: 10pt;
                border-collapse: collapse;
                direction: rtl;
            }}
            .totals-wrap td {{
                padding: 3.8pt 3pt;
                border-bottom: 1px solid #000000;
                font-size: 9pt;
                font-weight: 900;
            }}
            .totals-label {{ text-align: right; direction: rtl; }}
            .totals-value {{
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
            }}
            .remaining-row td {{
                border-top: 1px solid #000000;
                border-bottom: 2px solid #000000;
                font-size: 9.8pt;
            }}
            .payment-method {{
                margin: 7pt 0 0 0;
                text-align: center;
                direction: rtl;
                font-size: 8.8pt;
                font-weight: 900;
            }}
            .notes {{
                margin-top: 9pt;
                padding: 4pt;
                border: 1px solid #000000;
                text-align: right;
                direction: rtl;
                font-size: 7.8pt;
            }}
            .notes-title {{ margin-bottom: 3pt; font-weight: 900; }}
            .section-divider, .footer-divider {{
                margin-top: 11pt;
                border-top: 1px dashed #000000;
            }}
            .payment-block {{ margin-top: 7pt; text-align: center; }}
            .payment-title {{
                margin-bottom: 5pt;
                font-size: 9.4pt;
                font-weight: 900;
            }}
            .instapay-handle {{
                margin-top: 4pt;
                text-align: center;
                direction: ltr;
                font-family: "Arial", "DejaVu Sans";
                font-size: 8.2pt;
                font-weight: 900;
            }}
            .footer {{
                margin-top: 6pt;
                text-align: center;
                direction: rtl;
                font-size: 7.8pt;
                font-weight: 800;
            }}
            .bottom-space {{ height: 8pt; }}
        </style>
    </head>
    <body>
        <div class="receipt">
            <div class="header">
                {logo_html}
                <div class="company-ar">{_text(company_ar)}</div>
                <div class="company-en">{_text(company_en)}</div>
                <div class="address">{_text(settings.get("address"))}</div>
                <div class="phones">{phones_html}</div>
                <div class="invoice-title">فاتورة مبيعات</div>
            </div>

            <table class="meta" width="100%" cellspacing="0" cellpadding="0">
                {"".join(meta_rows)}
            </table>

            <table class="items" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                    <th width="42%">الصنف</th>
                    <th width="16%">الكمية</th>
                    <th width="19%">السعر</th>
                    <th width="23%">الإجمالي</th>
                </tr>
                {item_rows}
            </table>

            <table class="totals-wrap" width="88%" align="center" cellspacing="0" cellpadding="0">
                <tr>
                    <td class="totals-label" width="47%">الإجمالي</td>
                    <td class="totals-value" width="53%">{_money(invoice.get("total"))}</td>
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

            <div class="payment-method">طريقة الدفع: {payment_method}</div>
            {notes_html}
            {payment_html}
            {footer_html}
            <div class="bottom-space"></div>
        </div>
    </body>
    </html>
    """


__all__ = ["build_sales_receipt_html"]
