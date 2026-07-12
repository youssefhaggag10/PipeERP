from html import escape

from app.utils.datetime_utils import format_egypt_datetime


def _text(value: object) -> str:
    return escape(str(value or ""))


def _money(value: object) -> str:
    return f"{float(value or 0):,.2f}"


def build_sales_receipt_html(
    invoice: dict,
    settings: dict[str, str],
    *,
    logo_url: str = "",
    qr_url: str = "",
) -> str:
    phones = " — ".join(
        line.strip() for line in settings.get("phones", "").splitlines() if line.strip()
    )
    customer_details = [invoice.get("customer_name", "")]
    if invoice.get("customer_phone"):
        customer_details.append(invoice["customer_phone"])
    customer_text = " — ".join(_text(value) for value in customer_details if value)

    line_rows = []
    for index, line in enumerate(invoice.get("lines", []), start=1):
        line_rows.append(
            """
            <tr>
                <td class="product">{index}. {name}<br><span class="code">{code}</span></td>
                <td>{quantity:g}<br>{unit}</td>
                <td>{price}</td>
                <td>{total}</td>
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
        f'<div class="logo-wrap"><img class="logo" width="105" src="{logo_url}"></div>'
        if logo_url
        else ""
    )
    qr_html = ""
    if qr_url:
        qr_html = f"""
        <div class="payment">
            <div class="payment-title">الدفع عبر InstaPay</div>
            <img class="qr" width="116" src="{qr_url}">
            <div class="beneficiary">
                <strong>اسم المستفيد:</strong>
                {_text(settings.get('beneficiary_name'))}
            </div>
            <div class="handle">{_text(settings.get('instapay_handle'))}</div>
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
                font-size: 10pt;
                line-height: 1.25;
                margin: 0;
            }}
            .center {{ text-align: center; }}
            .logo-wrap {{ height: 82pt; margin: 0 0 2pt; text-align: center; }}
            .logo {{ width: 105px; }}
            .company {{ font-size: 13pt; font-weight: bold; margin: 2pt 0; }}
            .address {{ font-size: 9pt; margin-top: 1pt; }}
            .invoice-title {{
                border: 1px solid #000;
                font-size: 12pt;
                font-weight: bold;
                margin: 6pt 0 4pt;
                padding: 3pt 0;
            }}
            .muted {{ direction: ltr; font-size: 8.5pt; margin-top: 1pt; }}
            .separator {{ border-top: 1px dashed #000; margin: 4pt 0; }}
            .meta, .totals, .items {{ width: 100%; border-collapse: collapse; }}
            .meta td {{ padding: 1.5pt 1pt; vertical-align: top; }}
            .label {{ font-weight: bold; white-space: nowrap; }}
            .items th, .items td {{
                border-bottom: 1px solid #000;
                padding: 3pt 1pt;
                text-align: center;
                vertical-align: top;
            }}
            .items th {{
                border-bottom: 2px solid #000;
                border-top: 1px solid #000;
                font-size: 9pt;
                font-weight: bold;
            }}
            .items .product {{ width: 40%; text-align: right; }}
            .code {{ font-size: 7.5pt; }}
            .totals {{ margin-top: 3pt; }}
            .totals td {{ padding: 2pt 1pt; font-size: 10.5pt; }}
            .totals .value {{ text-align: left; font-weight: bold; }}
            .grand td {{ border-top: 2px solid #000; font-size: 12pt; font-weight: bold; }}
            .remaining td {{ border-bottom: 1px dashed #000; font-weight: bold; }}
            .payment {{ text-align: center; margin-top: 7pt; }}
            .payment-title {{ font-size: 10.5pt; font-weight: bold; margin-bottom: 2pt; }}
            .qr {{ width: 116px; }}
            .beneficiary {{ font-size: 8.5pt; margin-top: 2pt; }}
            .handle {{
                direction: ltr;
                font-family: Arial;
                font-weight: bold;
                font-size: 9pt;
                margin-top: 1pt;
            }}
            .hint {{ font-size: 7.5pt; margin-top: 2pt; }}
            .footer {{ text-align: center; font-size: 9pt; font-weight: bold; margin-top: 5pt; }}
        </style>
    </head>
    <body>
        <div class="center">
            {logo_html}
            <div class="company">{_text(settings.get('company_name'))}</div>
            <div class="address">{_text(settings.get('address'))}</div>
            <div class="muted">{_text(phones)}</div>
            <div class="invoice-title">فاتورة مبيعات</div>
        </div>
        <div class="separator"></div>
        <table class="meta">
            <tr><td class="label">رقم الفاتورة:</td><td>{invoice_number}</td></tr>
            <tr><td class="label">رقم الأمر:</td><td>{order_number}</td></tr>
            <tr><td class="label">التاريخ:</td><td>{invoice_date}</td></tr>
            <tr><td class="label">العميل:</td><td>{customer_text}</td></tr>
        </table>
        <div class="separator"></div>
        <table class="items">
            <thead><tr><th>الصنف</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr></thead>
            <tbody>{''.join(line_rows)}</tbody>
        </table>
        <table class="totals">
            <tr class="grand"><td>الإجمالي</td><td class="value">{invoice_total}</td></tr>
            <tr><td>المدفوع</td><td class="value">{invoice_paid}</td></tr>
            <tr class="remaining"><td>المتبقي</td><td class="value">{invoice_remaining}</td></tr>
            <tr><td>طريقة الدفع</td><td class="value">{payment_methods}</td></tr>
        </table>
        {qr_html}
        <div class="separator"></div>
        <div class="footer">{footer}</div>
    </body>
    </html>
    """
