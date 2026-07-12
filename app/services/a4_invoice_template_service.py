from html import escape

from app.utils.datetime_utils import format_egypt_datetime


def _text(value: object) -> str:
    return escape(str(value or ""))


def _money(value: object) -> str:
    return f"{float(value or 0):,.2f}"


def _company_parts(value: object) -> tuple[str, str]:
    text = str(value or "").strip()
    for separator in (" - ", " – ", " — "):
        if separator in text:
            arabic, english = text.split(separator, 1)
            return arabic.strip(), english.strip().upper()
    return text, ""


def _date_parts(value: object) -> tuple[str, str]:
    formatted = format_egypt_datetime(value)
    if " " not in formatted:
        return formatted, ""
    return tuple(formatted.split(" ", 1))


def _line_row(index: int, line: dict) -> str:
    quantity = float(line.get("quantity", 0) or 0)
    return f"""
        <tr>
            <td class="notes-cell" width="14%"></td>
            <td class="number-cell total-cell" width="15%">{_money(line.get("line_total"))}</td>
            <td class="number-cell" width="14%">{_money(line.get("unit_price"))}</td>
            <td class="number-cell" width="9%">{quantity:g}</td>
            <td class="center-cell" width="10%" dir="rtl">{_text(line.get("unit"))}</td>
            <td class="description-cell" width="33%" dir="rtl">
                <div class="product-name">{_text(line.get("name"))}</div>
                <div class="product-code" dir="ltr">{_text(line.get("code"))}</div>
            </td>
            <td class="center-cell" width="5%">{index}</td>
        </tr>
    """


def build_sales_invoice_a4_html(
    invoice: dict,
    settings: dict[str, str],
    *,
    logo_url: str = "",
    qr_url: str = "",
) -> str:
    company_ar, company_en = _company_parts(settings.get("company_name"))
    invoice_date, invoice_time = _date_parts(invoice.get("invoice_date"))
    phones = " &nbsp; | &nbsp; ".join(
        _text(line.strip()) for line in str(settings.get("phones", "")).splitlines() if line.strip()
    )
    rows = "".join(
        _line_row(index, line) for index, line in enumerate(invoice.get("lines", []), start=1)
    )
    if not rows:
        rows = '<tr><td colspan="7" class="empty-row">لا توجد أصناف</td></tr>'

    logo_html = f'<img src="{logo_url}" width="125">' if logo_url else ""
    qr_html = f'<img src="{qr_url}" width="92">' if qr_url else ""
    notes = _text(invoice.get("notes", "")).replace("\n", "<br>")
    footer = _text(settings.get("footer", "")).replace("\n", "<br>")
    instapay = _text(settings.get("instapay_handle"))

    return f"""
    <!DOCTYPE html>
    <html lang="ar">
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                color: #172033;
                background: #ffffff;
                font-family: "DejaVu Sans", "Tahoma", "Arial";
                font-size: 9pt;
            }}
            table {{ border-collapse: collapse; }}
            .header {{ width: 100%; background-color: #2f69a5; color: white; }}
            .header td {{ border: 0; padding: 10pt 12pt; vertical-align: middle; }}
            .logo-cell {{ width: 27%; text-align: left; background-color: white; }}
            .company-cell {{ width: 73%; text-align: right; direction: rtl; }}
            .company-ar {{ font-size: 18pt; font-weight: 900; }}
            .company-en {{ font-size: 12pt; font-weight: 800; direction: ltr; }}
            .company-detail {{ margin-top: 4pt; font-size: 8.5pt; }}
            .yellow-band {{ height: 8pt; background-color: #f5cc25; }}
            .title {{
                margin: 13pt 0 10pt 0;
                text-align: center;
                direction: rtl;
                color: #214f80;
                font-size: 18pt;
                font-weight: 900;
            }}
            .meta {{ width: 100%; margin-bottom: 10pt; }}
            .meta td {{ padding: 5pt 7pt; border: 1px solid #afbed0; }}
            .meta-label {{
                width: 16%;
                text-align: right;
                direction: rtl;
                background-color: #e8f0f8;
                color: #214f80;
                font-weight: 900;
            }}
            .meta-value {{ width: 34%; text-align: right; font-weight: 700; }}
            .items {{ width: 100%; border: 1px solid #233b58; }}
            .items th {{
                padding: 6pt 2pt;
                border: 1px solid #233b58;
                background-color: #f5cc25;
                color: #172033;
                text-align: center;
                direction: rtl;
                font-size: 8.2pt;
                font-weight: 900;
            }}
            .items td {{ padding: 7pt 3pt; border: 1px solid #697b90; vertical-align: middle; }}
            .description-cell {{ text-align: right; }}
            .product-name {{ font-weight: 900; }}
            .product-code {{ margin-top: 2pt; color: #53657a; font-size: 7.5pt; }}
            .number-cell {{ text-align: center; direction: ltr; font-family: "Arial"; }}
            .total-cell {{ font-weight: 900; }}
            .center-cell {{ text-align: center; }}
            .notes-cell {{ text-align: right; direction: rtl; }}
            .empty-row {{ padding: 18pt; text-align: center; direction: rtl; }}
            .totals {{ width: 62%; margin-top: 12pt; }}
            .totals td {{ padding: 6pt 9pt; border-bottom: 1px solid #8090a3; }}
            .totals-label {{
                width: 45%;
                text-align: right;
                direction: rtl;
                color: #214f80;
                font-weight: 900;
            }}
            .totals-value {{
                width: 55%;
                text-align: center;
                direction: ltr;
                font-size: 11pt;
                font-weight: 900;
            }}
            .remaining td {{ background-color: #8dcc45; color: #10230a; font-size: 12pt; }}
            .paid td {{ color: #b51d27; }}
            .lower {{ width: 100%; margin-top: 14pt; }}
            .lower td {{ border: 1px solid #afbed0; padding: 8pt; vertical-align: top; }}
            .section-title {{ color: #214f80; font-size: 10pt; font-weight: 900; direction: rtl; }}
            .section-text {{
                margin-top: 5pt;
                direction: rtl;
                text-align: right;
                font-size: 8.3pt;
            }}
            .payment-cell {{ width: 34%; text-align: center; }}
            .terms-cell {{ width: 66%; }}
            .instapay {{ margin-top: 3pt; direction: ltr; font-weight: 900; }}
            .footer {{ width: 100%; margin-top: 15pt; background-color: #2f69a5; color: white; }}
            .footer td {{ border: 0; padding: 8pt 10pt; }}
            .footer-left {{ width: 50%; text-align: left; direction: ltr; }}
            .footer-right {{ width: 50%; text-align: right; direction: rtl; }}
        </style>
    </head>
    <body>
        <table class="header" width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td class="logo-cell" width="27%">{logo_html}</td>
                <td class="company-cell" width="73%">
                    <div class="company-ar">{_text(company_ar)}</div>
                    <div class="company-en">{_text(company_en)}</div>
                    <div class="company-detail">{_text(settings.get("address"))}</div>
                    <div class="company-detail" dir="ltr">{phones}</div>
                </td>
            </tr>
        </table>
        <div class="yellow-band"></div>
        <div class="title">فاتورة مبيعات</div>

        <table class="meta" width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td class="meta-value" dir="rtl">{_text(invoice.get("customer_name"))}</td>
                <td class="meta-label">العميل</td>
                <td class="meta-value" dir="ltr">{_text(invoice.get("invoice_number"))}</td>
                <td class="meta-label">رقم الفاتورة</td>
            </tr>
            <tr>
                <td class="meta-value" dir="ltr">{_text(invoice.get("customer_phone"))}</td>
                <td class="meta-label">الهاتف</td>
                <td class="meta-value" dir="ltr">{_text(invoice.get("order_number"))}</td>
                <td class="meta-label">رقم الأمر</td>
            </tr>
            <tr>
                <td class="meta-value" dir="rtl">{_text(invoice.get("payment_methods") or "—")}</td>
                <td class="meta-label">طريقة الدفع</td>
                <td class="meta-value" dir="ltr">
                    {_text(invoice_date)} &nbsp; {_text(invoice_time)}
                </td>
                <td class="meta-label">التاريخ والوقت</td>
            </tr>
        </table>

        <table class="items" width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <th width="14%">ملاحظات</th>
                <th width="15%">الإجمالي</th>
                <th width="14%">سعر الوحدة</th>
                <th width="9%">الكمية</th>
                <th width="10%">الوحدة</th>
                <th width="33%">البيان</th>
                <th width="5%">م</th>
            </tr>
            {rows}
        </table>

        <table class="totals" width="62%" align="center" cellspacing="0" cellpadding="0">
            <tr>
                <td class="totals-value">{_money(invoice.get("total"))} جنيه</td>
                <td class="totals-label">الإجمالي</td>
            </tr>
            <tr class="paid">
                <td class="totals-value">{_money(invoice.get("paid"))} جنيه</td>
                <td class="totals-label">تم دفع</td>
            </tr>
            <tr class="remaining">
                <td class="totals-value">{_money(invoice.get("remaining"))} جنيه</td>
                <td class="totals-label">إجمالي المتبقي</td>
            </tr>
        </table>

        <table class="lower" width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td class="payment-cell" width="34%">
                    <div class="section-title">بيانات الدفع</div>
                    {qr_html}
                    <div class="instapay">{instapay}</div>
                </td>
                <td class="terms-cell" width="66%">
                    <div class="section-title">ملاحظات وشروط</div>
                    <div class="section-text">{notes or footer or "شكرًا لتعاملكم معنا."}</div>
                </td>
            </tr>
        </table>

        <table class="footer" width="100%" cellspacing="0" cellpadding="0">
            <tr>
                <td class="footer-left" width="50%">{phones}</td>
                <td class="footer-right" width="50%">{_text(settings.get("address"))}</td>
            </tr>
        </table>
    </body>
    </html>
    """


__all__ = ["build_sales_invoice_a4_html"]
