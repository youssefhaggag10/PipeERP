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

    logo_html = f'<img class="logo" src="{logo_url}">' if logo_url else ""
    qr_html = ""
    if qr_url:
        qr_html = f"""
        <div class="payment">
            <div class="payment-title">الدفع عبر InstaPay</div>
            <img class="qr" src="{qr_url}">
            <div><strong>اسم المستفيد:</strong> {_text(settings.get('beneficiary_name'))}</div>
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
                font-size: 9pt;
                margin: 0;
            }}
            .center {{ text-align: center; }}
            .logo {{ width: 42mm; max-height: 26mm; }}
            .company {{ font-size: 14pt; font-weight: bold; margin: 2px 0; }}
            .invoice-title {{ font-size: 12pt; font-weight: bold; margin: 5px 0; }}
            .muted {{ font-size: 8pt; }}
            .separator {{ border-top: 1px dashed #000; margin: 5px 0; }}
            .meta, .totals, .items {{ width: 100%; border-collapse: collapse; }}
            .meta td {{ padding: 1px 0; vertical-align: top; }}
            .label {{ font-weight: bold; white-space: nowrap; }}
            .items th, .items td {{
                border-bottom: 1px solid #000;
                padding: 3px 2px;
                text-align: center;
                vertical-align: top;
            }}
            .items th {{ font-size: 8pt; }}
            .items .product {{ width: 42%; text-align: right; }}
            .code {{ font-size: 7pt; }}
            .totals td {{ padding: 2px 0; font-size: 10pt; }}
            .totals .value {{ text-align: left; font-weight: bold; }}
            .grand td {{ border-top: 2px solid #000; font-size: 12pt; font-weight: bold; }}
            .payment {{ text-align: center; margin-top: 6px; }}
            .payment-title {{ font-size: 11pt; font-weight: bold; }}
            .qr {{ width: 47mm; max-height: 52mm; }}
            .handle {{ direction: ltr; font-family: Arial; font-weight: bold; font-size: 9pt; }}
            .hint {{ font-size: 7pt; margin-top: 2px; }}
            .footer {{ text-align: center; font-weight: bold; margin-top: 7px; }}
        </style>
    </head>
    <body>
        <div class="center">
            {logo_html}
            <div class="company">{_text(settings.get('company_name'))}</div>
            <div>{_text(settings.get('address'))}</div>
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
            <tr><td>المتبقي</td><td class="value">{invoice_remaining}</td></tr>
            <tr><td>طريقة الدفع</td><td class="value">{payment_methods}</td></tr>
        </table>
        {qr_html}
        <div class="separator"></div>
        <div class="footer">{footer}</div>
    </body>
    </html>
    """
