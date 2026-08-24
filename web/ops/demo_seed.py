#!/usr/bin/env python3
"""Create safe, repeatable PipeERP demo data through the public API."""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

MARKER = "[PIPEERP-DEMO-V1]"


class SeedError(RuntimeError):
    """Raised when the demo dataset cannot be created."""


class Api:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def login(self, username: str, password: str) -> None:
        self.request("POST", "/auth/login", {"username": username, "password": password})

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        key: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        csrf = next(
            (cookie.value for cookie in self.cookies if cookie.name == "pipeerp_csrf"), None
        )
        if method not in {"GET", "HEAD"} and csrf:
            headers["X-CSRF-Token"] = csrf
        if key:
            headers["Idempotency-Key"] = key
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except json.JSONDecodeError:
                pass
            raise SeedError(f"{method} {path}: HTTP {exc.code} - {detail}") from exc
        except URLError as exc:
            raise SeedError(f"تعذر الاتصال بـ {self.base_url}: {exc.reason}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any], key: str | None = None) -> Any:
        return self.request("POST", path, payload, key=key)


def find(items: list[dict[str, Any]], field: str, value: Any) -> dict[str, Any] | None:
    return next((item for item in items if item.get(field) == value), None)


def ensure(
    api: Api,
    list_path: str,
    create_path: str,
    field: str,
    value: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    existing = find(api.get(list_path), field, value)
    return existing if existing else api.post(create_path, payload)


def tagged(items: list[dict[str, Any]], field: str, name: str) -> dict[str, Any] | None:
    tag = f"{MARKER} {name}"
    return next((item for item in items if tag in str(item.get(field, ""))), None)


def progress(message: str) -> None:
    print(f"  ✓ {message}")


def seed_master_data(api: Api) -> dict[str, dict[str, Any]]:
    units = {
        "piece": ensure(
            api,
            "/master-data/units?include_inactive=true",
            "/master-data/units",
            "code",
            "DEMO-PC",
            {"code": "DEMO-PC", "name_ar": "قطعة ديمو", "symbol": "قطعة", "decimal_places": 0},
        ),
        "kg": ensure(
            api,
            "/master-data/units?include_inactive=true",
            "/master-data/units",
            "code",
            "DEMO-KG",
            {"code": "DEMO-KG", "name_ar": "كيلوجرام ديمو", "symbol": "كجم", "decimal_places": 3},
        ),
        "service": ensure(
            api,
            "/master-data/units?include_inactive=true",
            "/master-data/units",
            "code",
            "DEMO-SRV",
            {"code": "DEMO-SRV", "name_ar": "خدمة ديمو", "symbol": "خدمة", "decimal_places": 0},
        ),
    }
    categories = {
        "raw": ensure(
            api,
            "/master-data/categories?include_inactive=true",
            "/master-data/categories",
            "code",
            "DEMO-RAW",
            {"code": "DEMO-RAW", "name_ar": "خامات ديمو"},
        ),
        "finished": ensure(
            api,
            "/master-data/categories?include_inactive=true",
            "/master-data/categories",
            "code",
            "DEMO-FG",
            {"code": "DEMO-FG", "name_ar": "منتجات تامة ديمو"},
        ),
        "other": ensure(
            api,
            "/master-data/categories?include_inactive=true",
            "/master-data/categories",
            "code",
            "DEMO-OTHER",
            {"code": "DEMO-OTHER", "name_ar": "أصناف متنوعة ديمو"},
        ),
    }
    warehouse_rows = api.get("/master-data/warehouses")
    main_warehouse = next(
        (item for item in warehouse_rows if item.get("code") == "MAIN"),
        next((item for item in warehouse_rows if item.get("is_default")), None),
    )
    if main_warehouse is None:
        main_warehouse = api.post(
            "/master-data/warehouses",
            {"code": "MAIN", "name_ar": "المصنع", "is_default": True},
        )
    warehouses = {"main": main_warehouse}

    product_specs = {
        "raw": ("DEMO-RM-PVC", "خامة PVC ديمو", "raw_material", "kg", "raw", "250", "0"),
        "additive": ("DEMO-RM-ADD", "إضافات تصنيع ديمو", "raw_material", "kg", "raw", "25", "0"),
        "finished": (
            "DEMO-FG-110",
            "ماسورة PVC 110 مم ديمو",
            "finished_good",
            "piece",
            "finished",
            "20",
            "6",
        ),
        "waste": ("DEMO-WASTE", "كسر وهالك PVC ديمو", "waste", "kg", "other", "0", "0"),
        "spare": ("DEMO-SPARE", "قطعة غيار ماكينة ديمو", "spare_part", "piece", "other", "2", "0"),
        "service": ("DEMO-SERVICE", "خدمة نقل ديمو", "service", "service", "other", "0", "0"),
    }
    products: dict[str, dict[str, Any]] = {}
    for name, spec in product_specs.items():
        code, title, kind, unit, category, minimum, standard_weight = spec
        products[name] = ensure(
            api,
            "/master-data/products?include_inactive=true",
            "/master-data/products",
            "code",
            code,
            {
                "code": code,
                "name_ar": title,
                "product_type": kind,
                "unit_id": units[unit]["id"],
                "category_id": categories[category]["id"],
                "min_stock": minimum,
                "track_lots": kind != "service",
                "standard_weight_kg": standard_weight,
                "weight_tolerance_percent": "5" if kind == "finished_good" else "0",
            },
        )

    partners = {
        "supplier": ensure(
            api,
            "/master-data/partners?include_inactive=true",
            "/master-data/partners",
            "code",
            "DEMO-SUP-01",
            {
                "code": "DEMO-SUP-01",
                "name_ar": "شركة الخامات للديمو",
                "phone": "01000000101",
                "address": "القاهرة - عنوان تجريبي",
                "tax_number": "DEMO-TAX-SUP",
                "is_customer": False,
                "is_supplier": True,
            },
        ),
        "customer": ensure(
            api,
            "/master-data/partners?include_inactive=true",
            "/master-data/partners",
            "code",
            "DEMO-CUS-01",
            {
                "code": "DEMO-CUS-01",
                "name_ar": "عميل الجملة للديمو",
                "phone": "01000000202",
                "address": "الجيزة - عنوان تجريبي",
                "tax_number": "DEMO-TAX-CUS",
                "is_customer": True,
                "is_supplier": False,
            },
        ),
        "customer2": ensure(
            api,
            "/master-data/partners?include_inactive=true",
            "/master-data/partners",
            "code",
            "DEMO-CUS-02",
            {
                "code": "DEMO-CUS-02",
                "name_ar": "عميل التجزئة للديمو",
                "phone": "01000000303",
                "address": "الإسكندرية - عنوان تجريبي",
                "tax_number": "",
                "is_customer": True,
                "is_supplier": False,
            },
        ),
    }
    progress("الأصناف والوحدات والمخازن والعملاء والموردون")
    return {**products, **partners, **warehouses}


def seed_accounts(api: Api) -> dict[str, dict[str, Any]]:
    cash = ensure(
        api,
        "/accounts/financial-accounts?include_inactive=true",
        "/accounts/financial-accounts",
        "code",
        "DEMO-CASH",
        {
            "code": "DEMO-CASH",
            "name_ar": "خزينة الديمو",
            "account_type": "cash",
            "opening_balance": "50000",
            "is_default": False,
            "notes": MARKER,
        },
    )
    bank = ensure(
        api,
        "/accounts/financial-accounts?include_inactive=true",
        "/accounts/financial-accounts",
        "code",
        "DEMO-BANK",
        {
            "code": "DEMO-BANK",
            "name_ar": "بنك الديمو",
            "account_type": "bank",
            "opening_balance": "100000",
            "is_default": False,
            "notes": MARKER,
        },
    )
    progress("الخزينة والحساب البنكي")
    return {"cash": cash, "bank": bank}


def seed_inventory(api: Api, data: dict[str, dict[str, Any]]) -> None:
    receipts = [
        ("raw", "2500", "0", "quantity", "25", "DEMO-PVC-A"),
        ("additive", "300", "0", "quantity", "40", "DEMO-ADD-A"),
        ("finished", "120", "720", "weight", "22", "DEMO-FG-A"),
        ("spare", "10", "0", "quantity", "350", "DEMO-SP-A"),
    ]
    for name, quantity, weight, basis, cost, lot in receipts:
        api.post(
            "/inventory/receipts",
            {
                "product_id": data[name]["id"],
                "warehouse_id": data["main"]["id"],
                "quantity": quantity,
                "weight_kg": weight,
                "cost_basis": basis,
                "unit_cost": cost,
                "lot_number": lot,
                "reference_type": "demo_seed",
                "reference_id": "PIPEERP-DEMO-V1",
                "notes": MARKER,
            },
            f"pipeerp-demo-v1-receipt-{name}",
        )
    progress("أرصدة المخزون والدفعات على مخزن المصنع")


def seed_purchase(api: Api, data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    orders = api.get("/purchases/orders?limit=500")
    order = tagged(orders, "notes", "purchase")
    if order is None:
        order = api.post(
            "/purchases/orders",
            {
                "supplier_id": data["supplier"]["id"],
                "warehouse_id": data["main"]["id"],
                "notes": f"{MARKER} purchase",
                "advance_amount": "0",
                "lines": [
                    {
                        "product_id": data["raw"]["id"],
                        "cost_basis": "quantity",
                        "ordered_quantity": "800",
                        "ordered_weight_kg": "0",
                        "unit_price": "26",
                        "additional_unit_cost": "1",
                        "purchase_loss_quantity": "4",
                    },
                    {
                        "product_id": data["additive"]["id"],
                        "cost_basis": "quantity",
                        "ordered_quantity": "200",
                        "ordered_weight_kg": "0",
                        "unit_price": "42",
                        "additional_unit_cost": "0",
                        "purchase_loss_quantity": "1",
                    },
                ],
            },
        )
    if order["status"] in {"draft", "approved", "partially_received"}:
        order = api.post(
            f"/purchases/orders/{order['id']}/receive",
            {"version": order["version"]},
            "pipeerp-demo-v1-purchase-receive",
        )
    progress("أمر شراء مستلم ومُرحّل تلقائياً مع فاتورة المورد")
    return order


def _find_sales_order(api: Api, name: str) -> dict[str, Any] | None:
    return tagged(api.get("/sales/orders?limit=500"), "notes", name)


def seed_sales(api: Api, data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    piece = _find_sales_order(api, "piece-sale")
    if piece is None:
        piece = api.post(
            "/sales/orders",
            {
                "customer_id": data["customer"]["id"],
                "warehouse_id": data["main"]["id"],
                "notes": f"{MARKER} piece-sale",
                "advance_amount": "0",
                "lines": [
                    {
                        "product_id": data["finished"]["id"],
                        "quantity": "12",
                        "unit": "ماسورة",
                        "unit_price": "220",
                        "notes": "بيع بالقطعة",
                    }
                ],
            },
        )
    if piece["status"] == "draft":
        piece = api.post(
            f"/sales/orders/{piece['id']}/delivery",
            {"version": piece["version"]},
            "pipeerp-demo-v1-piece-delivery",
        )

    weight = _find_sales_order(api, "weight-sale")
    if weight is None:
        weight = api.post(
            "/sales/weight-orders",
            {
                "customer_id": data["customer2"]["id"],
                "warehouse_id": data["main"]["id"],
                "weight_mode": "per_line",
                "pricing_mode": "per_line",
                "use_vehicle_scale": False,
                "discount_amount": "50",
                "transport_amount": "200",
                "tax_amount": "0",
                "notes": f"{MARKER} weight-sale",
                "advance_amount": "0",
                "lines": [
                    {
                        "product_id": data["finished"]["id"],
                        "quantity": "8",
                        "unit": "ماسورة",
                        "actual_weight_kg": "47.5",
                        "price_per_kg": "38",
                        "notes": "بيع بوزن فعلي",
                    }
                ],
            },
        )
    if weight["status"] == "draft":
        api.post(
            f"/sales/orders/{weight['id']}/delivery",
            {"version": weight["version"]},
            "pipeerp-demo-v1-weight-delivery",
        )

    if _find_sales_order(api, "draft-sale") is None:
        api.post(
            "/sales/orders",
            {
                "customer_id": data["customer2"]["id"],
                "warehouse_id": data["main"]["id"],
                "notes": f"{MARKER} draft-sale",
                "advance_amount": "0",
                "lines": [
                    {
                        "product_id": data["finished"]["id"],
                        "quantity": "3",
                        "unit": "ماسورة",
                        "unit_price": "230",
                        "notes": "اتركه مسودة للاختبار",
                    }
                ],
            },
        )

    quotations = api.get("/sales/quotations?limit=500")
    if tagged(quotations, "notes", "quotation") is None:
        api.post(
            "/sales/quotations",
            {
                "customer_id": data["customer"]["id"],
                "valid_until": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                "notes": f"{MARKER} quotation",
                "lines": [
                    {
                        "product_id": data["finished"]["id"],
                        "item_name": "ماسورة PVC 110 مم",
                        "quantity": "25",
                        "unit": "ماسورة",
                        "unit_price": "215",
                        "notes": "عرض سعر ديمو",
                    },
                    {
                        "product_id": data["service"]["id"],
                        "item_name": "خدمة نقل",
                        "quantity": "1",
                        "unit": "خدمة",
                        "unit_price": "750",
                        "notes": "",
                    },
                ],
            },
        )
    progress("بيع بالقطعة والوزن، فاتورتان، أمر مسودة وعرض سعر")
    return api.get(f"/sales/orders/{piece['id']}")


def seed_manufacturing(api: Api, data: dict[str, dict[str, Any]]) -> None:
    recipes = api.get("/manufacturing/recipes?include_inactive=true")
    recipe = find(recipes, "code", "DEMO-RECIPE-PVC")
    if recipe is None:
        recipe = api.post(
            "/manufacturing/recipes",
            {
                "code": "DEMO-RECIPE-PVC",
                "name_ar": "خلطة PVC تجريبية",
                "output_product_ids": [data["finished"]["id"]],
                "components": [
                    {"product_id": data["raw"]["id"], "quantity_per_batch": "90"},
                    {"product_id": data["additive"]["id"], "quantity_per_batch": "10"},
                ],
                "suggested_scrap_per_batch": "2",
                "notes": MARKER,
            },
        )
    orders = api.get("/manufacturing/orders?limit=500")
    order = tagged(orders, "notes", "manufacturing-in-progress")
    if order is None:
        order = api.post(
            "/manufacturing/orders",
            {
                "recipe_id": recipe["id"],
                "warehouse_id": data["main"]["id"],
                "outputs": [{"product_id": data["finished"]["id"], "quantity": "20"}],
                "scrap_inputs": [],
                "notes": f"{MARKER} manufacturing-in-progress",
            },
            "pipeerp-demo-v1-manufacturing-order",
        )
    if order["status"] == "draft":
        api.post(
            f"/manufacturing/orders/{order['id']}/start",
            {"version": order["version"]},
            "pipeerp-demo-v1-manufacturing-start",
        )
    progress("خلطة تصنيع وأمر تحت التشغيل جاهز لاختبار الإكمال")


def seed_crm(api: Api) -> None:
    phone = "01000000999"
    lead = find(api.get(f"/crm/leads?search={phone}"), "phone", phone)
    if lead is None:
        owners = api.get("/crm/options")["owners"]
        if not owners:
            raise SeedError("تعذر إنشاء عميل CRM: لا يوجد مسؤول متابعة نشط")
        lead = api.post(
            "/crm/leads",
            {
                "name": "عميل محتمل ديمو",
                "phone": phone,
                "alternate_phone": "",
                "company": "شركة مشروعات الديمو",
                "address": "القاهرة الجديدة - عنوان تجريبي",
                "source_code": "referral",
                "customer_type": "potential",
                "temperature": "hot",
                "stage_code": "negotiation",
                "assigned_user_id": owners[0]["id"],
                "interested_products": "مواسير PVC 110 مم",
                "tags": "ديمو، أولوية",
                "opportunity_value": "75000",
                "general_notes": MARKER,
                "lost_reason": "",
            },
        )
    scheduled = api.get("/crm/activities?status=scheduled")
    if not any(item["lead_id"] == lead["id"] and MARKER in item["notes"] for item in scheduled):
        api.post(
            f"/crm/leads/{lead['id']}/activities",
            {
                "activity_type": "call",
                "subject": "متابعة عرض سعر الديمو",
                "notes": MARKER,
                "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "priority": "high",
            },
        )
    progress("عميل محتمل ساخن ومتابعة مجدولة في CRM")


def seed_return(api: Api, sale: dict[str, Any]) -> None:
    documents = api.get("/returns/documents?limit=500")
    if tagged(documents, "reason", "partial-sales-return") is None:
        invoice = sale.get("invoice")
        if invoice is None:
            raise SeedError("تعذر إنشاء المرتجع: فاتورة بيع الديمو غير موجودة")
        api.post(
            "/returns/documents",
            {
                "return_type": "sales",
                "invoice_id": invoice["id"],
                "reason": f"{MARKER} partial-sales-return",
                "lines": [
                    {"source_line_id": sale["lines"][0]["id"], "quantity": "2", "weight_kg": "0"}
                ],
            },
            "pipeerp-demo-v1-partial-sales-return",
        )
    progress("مرتجع بيع جزئي يعيد المخزون ويخفض رصيد العميل")


def seed_treasury(
    api: Api,
    data: dict[str, dict[str, Any]],
    accounts: dict[str, dict[str, Any]],
    purchase: dict[str, Any],
    sale: dict[str, Any],
) -> None:
    sale_invoice = sale.get("invoice")
    supplier_invoice = purchase.get("supplier_invoice")
    if sale_invoice is None or supplier_invoice is None:
        raise SeedError("تعذر إنشاء الحركات المالية: فواتير الديمو غير مكتملة")
    api.post(
        "/accounts/payments",
        {
            "transaction_type": "customer_receipt",
            "partner_id": data["customer"]["id"],
            "financial_account_id": accounts["cash"]["id"],
            "amount": "500",
            "payment_method": "cash",
            "allocations": [{"invoice_id": sale_invoice["id"], "amount": "500"}],
            "notes": f"{MARKER} customer-receipt",
        },
        "pipeerp-demo-v1-customer-receipt",
    )
    api.post(
        "/accounts/payments",
        {
            "transaction_type": "supplier_payment",
            "partner_id": data["supplier"]["id"],
            "financial_account_id": accounts["bank"]["id"],
            "amount": "5000",
            "payment_method": "bank_transfer",
            "allocations": [{"invoice_id": supplier_invoice["id"], "amount": "5000"}],
            "notes": f"{MARKER} supplier-payment",
        },
        "pipeerp-demo-v1-supplier-payment",
    )
    opening = api.get("/accounts/opening-balances")
    if tagged(opening, "notes", "customer-opening") is None:
        api.post(
            "/accounts/opening-balances",
            {
                "partner_id": data["customer2"]["id"],
                "nature": "debit",
                "amount": "1500",
                "entry_date": date.today().isoformat(),
                "notes": f"{MARKER} customer-opening",
            },
        )
    adjustments = api.get("/accounts/customer-adjustments")
    if tagged(adjustments, "notes", "customer-credit") is None:
        api.post(
            "/accounts/customer-adjustments",
            {
                "customer_id": data["customer"]["id"],
                "adjustment_type": "credit",
                "amount": "100",
                "notes": f"{MARKER} customer-credit",
            },
        )
    progress("تحصيل وسداد وتوزيع فواتير وأرصدة افتتاحية وتسويات")


def local_api(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise SeedError("للأمان تعمل أداة الديمو على localhost فقط")
    return url.rstrip("/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="إنشاء بيانات ديمو مترابطة وآمنة في PipeERP عبر الـ API"
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000/api/v1",
        help="رابط API المحلي (الافتراضي: %(default)s)",
    )
    parser.add_argument("--username", default="admin", help="اسم مستخدم المدير")
    parser.add_argument("--yes", action="store_true", help="تخطي رسالة التأكيد")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        api_url = local_api(args.api_url)
        if not args.yes:
            answer = input(
                "ستُضاف بيانات Demo فقط، من دون حذف بيانات أو تغيير كلمات سر. متابعة؟ [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                print("تم الإلغاء دون أي تغيير.")
                return 0
        password = os.environ.get("PIPEERP_DEMO_ADMIN_PASSWORD") or getpass.getpass(
            f"كلمة مرور {args.username}: "
        )
        api = Api(api_url)
        print("\nجاري إنشاء بيانات PipeERP التجريبية:")
        api.login(args.username, password)
        progress("تسجيل الدخول والتحقق من الصلاحيات")
        data = seed_master_data(api)
        accounts = seed_accounts(api)
        seed_inventory(api, data)
        purchase = seed_purchase(api, data)
        sale = seed_sales(api, data)
        seed_manufacturing(api, data)
        seed_crm(api)
        seed_return(api, sale)
        seed_treasury(api, data, accounts, purchase, sale)
    except (SeedError, KeyboardInterrupt) as exc:
        print(f"\n✗ توقف إنشاء البيانات: {exc}", file=sys.stderr)
        return 1
    print(
        "\nتم تجهيز بيانات الديمو. يمكنك تشغيل الأداة مرة أخرى بأمان؛ "
        "لن تضاعف المستندات التشغيلية نفسها."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
