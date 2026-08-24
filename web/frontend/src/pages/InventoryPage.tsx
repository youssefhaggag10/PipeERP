import {
  Check,
  Layers3,
  PackageSearch,
  RefreshCw,
  SlidersHorizontal,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { clientId } from "../lib/clientId";

type InventoryOption = { id: string; code: string; name_ar: string };
type InventoryOptions = {
  products: InventoryOption[];
  warehouses: InventoryOption[];
};
type Balance = {
  product_id: string;
  warehouse_id: string;
  quantity_on_hand: string;
  product_code: string;
  product_name_ar: string;
  product_type: string;
  unit_symbol: string;
};
type LotBalance = {
  lot_id: string;
  warehouse_id: string;
  product_code: string;
  product_name_ar: string;
  warehouse_name_ar: string;
  lot_number: string;
  received_at: string;
  quantity_received: string;
  quantity_issued: string;
  quantity_remaining: string;
  average_cost: string;
  inventory_value: string;
};
type StockCardLine = {
  id: string;
  warehouse_id: string;
  product_code: string;
  product_name_ar: string;
  warehouse_name_ar: string;
  lot_number: string;
  quantity_in: string;
  quantity_out: string;
  unit_cost: string;
  reference_type: string;
  partner_name_ar: string;
  posted_at: string;
};
type InventoryView = "balances" | "lots" | "stock-card";

const productTypeLabels: Record<string, string> = {
  raw_material: "خامة",
  finished_good: "منتج نهائي",
  waste: "هالك",
  service: "خدمة",
  spare_part: "قطعة غيار",
};
const referenceLabels: Record<string, string> = {
  purchase_receipt: "شراء",
  sales_delivery: "بيع",
  sales_return: "مرتجع بيع",
  purchase_return: "مرتجع شراء",
  manufacturing_material_issue: "تصنيع",
  manufacturing_output: "تصنيع",
  manufacturing_unused_return: "تصنيع",
  manufacturing_scrap: "تصنيع",
  stock_adjustment: "تسوية",
  adjustment: "تسوية",
};
const numberFormat = new Intl.NumberFormat("ar-EG", {
  maximumFractionDigits: 3,
});
const costFormat = new Intl.NumberFormat("ar-EG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});
const number = (value: string | number) => numberFormat.format(Number(value));

export function InventoryPage() {
  const { user } = useAuth();
  const location = useLocation();
  const canManage = user?.permissions.includes("inventory.manage") ?? false;
  const requestedView = new URLSearchParams(location.search).get("view");
  const view: InventoryView =
    requestedView === "lots" || requestedView === "stock-card"
      ? requestedView
      : "balances";
  const [balances, setBalances] = useState<Balance[]>([]);
  const [lots, setLots] = useState<LotBalance[]>([]);
  const [stockCard, setStockCard] = useState<StockCardLine[]>([]);
  const [options, setOptions] = useState<InventoryOptions>({
    products: [],
    warehouses: [],
  });
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitCost, setUnitCost] = useState("0");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const optionRows = await api<InventoryOptions>("/inventory/options");
      const factoryWarehouse =
        optionRows.warehouses.find((item) => item.code === "MAIN") ??
        optionRows.warehouses[0];
      setOptions({
        products: optionRows.products,
        warehouses: factoryWarehouse ? [factoryWarehouse] : [],
      });
      if (view === "balances") {
        const balanceRows = await api<Balance[]>("/inventory/balances");
        setBalances(
          factoryWarehouse
            ? balanceRows.filter((item) => item.warehouse_id === factoryWarehouse.id)
            : balanceRows,
        );
        setProductId((current) => current || optionRows.products[0]?.id || "");
      } else if (view === "lots") {
        const lotRows = await api<LotBalance[]>("/inventory/lot-balances");
        setLots(
          factoryWarehouse
            ? lotRows.filter((item) => item.warehouse_id === factoryWarehouse.id)
            : lotRows,
        );
      } else {
        const stockRows = await api<StockCardLine[]>("/inventory/stock-card?limit=500");
        setStockCard(
          factoryWarehouse
            ? stockRows.filter((item) => item.warehouse_id === factoryWarehouse.id)
            : stockRows,
        );
      }
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "تعذر تحميل بيانات المخزون",
      );
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submitAdjustment(event: FormEvent) {
    event.preventDefault();
    const signedQuantity = Number(quantity);
    const warehouseId = options.warehouses[0]?.id;
    if (
      !productId ||
      !warehouseId ||
      !Number.isFinite(signedQuantity) ||
      signedQuantity === 0
    ) {
      setError("اختار صنف واكتب كمية تسوية صحيحة لا تساوي صفرًا");
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await api("/inventory/adjustments", {
        method: "POST",
        headers: { "Idempotency-Key": clientId("inventory-adjustment") },
        body: JSON.stringify({
          product_id: productId,
          warehouse_id: warehouseId,
          direction: signedQuantity > 0 ? "increase" : "decrease",
          quantity: String(Math.abs(signedQuantity)),
          weight_kg: "0",
          cost_basis: "quantity",
          unit_cost: unitCost || "0",
          reason: notes,
        }),
      });
      setQuantity("");
      setUnitCost("0");
      setNotes("");
      setNotice("تم تسجيل تسوية الصنف وتحديث رصيد المخزون.");
      await load();
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "تعذر تسجيل التسوية",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const heading =
    view === "balances"
      ? "رصيد المخزون"
      : view === "lots"
        ? "أرصدة الدفعات"
        : "كارت الصنف";
  const subtitle =
    view === "balances"
      ? "الرصيد ناتج من حركات المخزون فقط. استخدم التسوية للرصيد الافتتاحي أو الجرد."
      : view === "lots"
        ? "الرصيد والقيمة المتبقية لكل دفعة وفق الصرف بنظام FIFO."
        : "كل حركات الصنف داخل وخارج بالمخزن والتشغيلة والمرجع.";

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <h2>{heading}</h2>
          <p>{subtitle}</p>
        </div>
        <button
          className="secondary-button"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw size={17} /> تحديث
        </button>
      </section>
      {error ? (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="alert alert--success">
          <Check size={17} />
          {notice}
        </div>
      ) : null}

      {view === "balances" ? (
        <>
          {canManage ? (
            <form
              className="panel inventory-adjustment-form"
              onSubmit={submitAdjustment}
            >
              <label>
                الصنف
                <select
                  value={productId}
                  onChange={(event) => setProductId(event.target.value)}
                  required
                >
                  {options.products.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name_ar} · {item.code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                كمية التسوية
                <input
                  type="number"
                  step="0.001"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  placeholder="موجب للإضافة، سالب للخصم"
                  required
                />
              </label>
              <label>
                تكلفة الوحدة للإضافة
                <input
                  type="number"
                  min="0"
                  step="0.0001"
                  value={unitCost}
                  onChange={(event) => setUnitCost(event.target.value)}
                />
              </label>
              <label>
                رقم الدفعة
                <input
                  readOnly
                  value=""
                  placeholder="يُنشئ النظام رقم الدفعة تلقائيًا"
                />
              </label>
              <label>
                ملاحظات
                <input
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              </label>
              <button
                className="primary-button"
                disabled={
                  submitting ||
                  !options.products.length ||
                  !options.warehouses.length
                }
              >
                <SlidersHorizontal size={17} /> تسجيل تسوية للصنف المحدد
              </button>
            </form>
          ) : null}
          <section className="panel">
            {balances.length ? (
              <div className="data-table-wrap">
                <table className="data-table inventory-table">
                  <thead>
                    <tr>
                      <th>الكود</th>
                      <th>الصنف</th>
                      <th>النوع</th>
                      <th>الوحدة</th>
                      <th>الرصيد الحالي</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balances.map((item) => (
                      <tr key={`${item.product_id}-${item.warehouse_id}`}>
                        <td dir="ltr">{item.product_code}</td>
                        <td>{item.product_name_ar}</td>
                        <td>
                          {productTypeLabels[item.product_type] ??
                            item.product_type}
                        </td>
                        <td>{item.unit_symbol}</td>
                        <td className="numeric-cell">
                          <strong>{number(item.quantity_on_hand)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                icon={<PackageSearch size={27} />}
                title="لا توجد أرصدة حتى الآن"
              />
            )}
          </section>
        </>
      ) : view === "lots" ? (
        <section className="panel">
          {lots.length ? (
            <div className="data-table-wrap">
              <table className="data-table inventory-table">
                <thead>
                  <tr>
                    <th>الكود</th>
                    <th>الصنف</th>
                    <th>المخزن</th>
                    <th>رقم الدفعة</th>
                    <th>تاريخ الاستلام</th>
                    <th>المستلم</th>
                    <th>المصروف</th>
                    <th>المتبقي</th>
                    <th>متوسط التكلفة</th>
                    <th>القيمة</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((item) => (
                    <tr key={item.lot_id}>
                      <td dir="ltr">{item.product_code}</td>
                      <td>{item.product_name_ar}</td>
                      <td>{item.warehouse_name_ar}</td>
                      <td dir="ltr">{item.lot_number}</td>
                      <td>
                        {new Date(item.received_at).toLocaleString("ar-EG")}
                      </td>
                      <td className="numeric-cell">
                        {number(item.quantity_received)}
                      </td>
                      <td className="numeric-cell">
                        {number(item.quantity_issued)}
                      </td>
                      <td className="numeric-cell">
                        <strong>{number(item.quantity_remaining)}</strong>
                      </td>
                      <td className="numeric-cell">
                        {costFormat.format(Number(item.average_cost))}
                      </td>
                      <td className="numeric-cell">
                        {costFormat.format(Number(item.inventory_value))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              icon={<Layers3 size={27} />}
              title="لا توجد دفعات حتى الآن"
            />
          )}
        </section>
      ) : (
        <section className="panel">
          {stockCard.length ? (
            <div className="data-table-wrap">
              <table className="data-table inventory-table stock-card-table">
                <thead>
                  <tr>
                    <th>التاريخ</th>
                    <th>الكود</th>
                    <th>الصنف</th>
                    <th>المخزن</th>
                    <th>الدفعة</th>
                    <th>داخل</th>
                    <th>خارج</th>
                    <th>التكلفة</th>
                    <th>المرجع</th>
                    <th>الطرف</th>
                  </tr>
                </thead>
                <tbody>
                  {stockCard.map((item) => (
                    <tr key={item.id}>
                      <td>
                        {new Date(item.posted_at).toLocaleString("ar-EG")}
                      </td>
                      <td dir="ltr">{item.product_code}</td>
                      <td>{item.product_name_ar}</td>
                      <td>{item.warehouse_name_ar}</td>
                      <td dir="ltr">{item.lot_number || "—"}</td>
                      <td className="numeric-cell">
                        {Number(item.quantity_in)
                          ? number(item.quantity_in)
                          : "—"}
                      </td>
                      <td className="numeric-cell">
                        {Number(item.quantity_out)
                          ? number(item.quantity_out)
                          : "—"}
                      </td>
                      <td className="numeric-cell">
                        {costFormat.format(Number(item.unit_cost))}
                      </td>
                      <td>
                        {referenceLabels[item.reference_type] ??
                          item.reference_type}
                      </td>
                      <td>{item.partner_name_ar || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              icon={<PackageSearch size={27} />}
              title="لا توجد حركات حتى الآن"
            />
          )}
        </section>
      )}
    </AppShell>
  );
}

function Empty({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon">{icon}</span>
      <h4>{title}</h4>
    </div>
  );
}
