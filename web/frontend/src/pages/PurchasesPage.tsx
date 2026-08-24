import {
  Check,
  FilePlus2,
  PackageCheck,
  Plus,
  ReceiptText,
  RefreshCw,
  Scale,
  Trash2,
  Truck,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { clientId } from "../lib/clientId";

type OrderStatus = "draft" | "approved" | "partially_received" | "received" | "cancelled";

type Option = {
  id: string;
  code: string;
  name_ar: string;
  account_type: string;
  unit_symbol: string;
};

type PurchaseOptions = {
  suppliers: Option[];
  warehouses: Option[];
  products: Option[];
  financial_accounts: Option[];
};

type OrderLine = {
  id: string;
  product_id: string;
  product_code: string;
  product_name_ar: string;
  ordered_quantity: string;
  received_quantity: string;
  unit_price: string;
  additional_unit_cost: string;
  lot_number: string;
  purchase_loss_quantity: string;
  net_quantity: string;
  inventory_unit_cost: string;
  line_total: string;
  version: number;
};

type SupplierInvoice = {
  id: string;
  invoice_number: string;
  supplier_invoice_number: string;
  status: "draft" | "posted" | "reversed";
  total: string;
  version: number;
};

type PurchaseOrder = {
  id: string;
  order_number: string;
  supplier_id: string;
  supplier_code: string;
  supplier_name_ar: string;
  warehouse_id: string;
  warehouse_name_ar: string;
  status: OrderStatus;
  order_date: string;
  notes: string;
  total: string;
  version: number;
  lines: OrderLine[];
  supplier_invoice: SupplierInvoice | null;
};

type DraftLine = {
  key: string;
  product_id: string;
  quantity: string;
  unit_price: string;
  internal_unit_cost: string;
  purchase_loss: string;
};

const currency = new Intl.NumberFormat("ar-EG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const number = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 4 });

const statusMeta: Record<OrderStatus, { label: string; className: string }> = {
  draft: { label: "مسودة", className: "purchase-status--draft" },
  approved: { label: "مسودة قديمة", className: "purchase-status--draft" },
  partially_received: { label: "استلام غير مكتمل", className: "purchase-status--partial" },
  received: { label: "تم الاستلام", className: "purchase-status--received" },
  cancelled: { label: "ملغي", className: "purchase-status--cancelled" },
};

function newDraftLine(productId = ""): DraftLine {
  return {
    key: clientId("purchase-line"),
    product_id: productId,
    quantity: "",
    unit_price: "0",
    internal_unit_cost: "0",
    purchase_loss: "",
  };
}

function defaultLoss(quantity: string, product: Option | undefined): string {
  const value = Number(quantity);
  if (!Number.isFinite(value) || value <= 0) return "";
  if (!["كجم", "kg"].includes(product?.unit_symbol.trim().toLocaleLowerCase() ?? "")) return "0";
  return String(Math.round(value * 0.005 * 1_000_000) / 1_000_000);
}

export function PurchasesPage() {
  const { user } = useAuth();
  const location = useLocation();
  const canManage = user?.permissions.includes("purchases.manage") ?? false;
  const requestedFocus = new URLSearchParams(location.search).get("focus");
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [options, setOptions] = useState<PurchaseOptions>({ suppliers: [], warehouses: [], products: [], financial_accounts: [] });
  const [selectedId, setSelectedId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [notes, setNotes] = useState("");
  const [draftLines, setDraftLines] = useState<DraftLine[]>([newDraftLine()]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showCreate, setShowCreate] = useState(requestedFocus === "new");
  const createRef = useRef<HTMLElement>(null);
  const detailRef = useRef<HTMLElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [orderRows, optionRows] = await Promise.all([
        api<PurchaseOrder[]>("/purchases/orders?limit=150"),
        api<PurchaseOptions>("/purchases/options"),
      ]);
      const factoryWarehouse = optionRows.warehouses.find((item) => item.code === "MAIN") ?? optionRows.warehouses[0];
      setOrders(orderRows);
      setOptions({ ...optionRows, warehouses: factoryWarehouse ? [factoryWarehouse] : [] });
      setSelectedId((current) => current || orderRows[0]?.id || "");
      setSupplierId((current) => current || optionRows.suppliers[0]?.id || "");
      setDraftLines((current) => current.map((line) => ({ ...line, product_id: line.product_id || optionRows.products[0]?.id || "" })));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل المشتريات");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (requestedFocus === "new") {
      setShowCreate(true);
      window.requestAnimationFrame(() => createRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } else if (requestedFocus === "receipt") {
      window.requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }, [requestedFocus]);

  const selected = orders.find((item) => item.id === selectedId) ?? null;
  const draftTotal = useMemo(() => draftLines.reduce((sum, line) => sum + Number(line.quantity || 0) * Number(line.unit_price || 0), 0), [draftLines]);

  function updateDraftLine(key: string, patch: Partial<DraftLine>) {
    setDraftLines((current) => current.map((line) => line.key === key ? { ...line, ...patch } : line));
  }

  function updateQuantity(line: DraftLine, quantity: string) {
    const product = options.products.find((item) => item.id === line.product_id);
    updateDraftLine(line.key, { quantity, purchase_loss: defaultLoss(quantity, product) });
  }

  function selectOrder(orderId: string) {
    setSelectedId(orderId);
    setShowCreate(false);
    window.requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  async function submitOrder(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const created = await api<PurchaseOrder>("/purchases/orders", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: supplierId,
          warehouse_id: options.warehouses[0]?.id ?? null,
          notes,
          advance_amount: "0",
          lines: draftLines.map((line) => ({
            product_id: line.product_id,
            cost_basis: "quantity",
            ordered_quantity: line.quantity,
            ordered_weight_kg: "0",
            unit_price: line.unit_price || "0",
            additional_unit_cost: line.internal_unit_cost || "0",
            purchase_loss_quantity: line.purchase_loss || "0",
          })),
        }),
      });
      setNotes("");
      setDraftLines([newDraftLine(options.products[0]?.id || "")]);
      setShowCreate(false);
      setNotice(`تم حفظ أمر الشراء ${created.order_number} كمسودة.`);
      setSelectedId(created.id);
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر حفظ أمر الشراء");
    } finally {
      setSubmitting(false);
    }
  }

  async function receiveSelected() {
    if (!selected) return;
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await api(`/purchases/orders/${selected.id}/receive`, {
        method: "POST",
        headers: { "Idempotency-Key": clientId("purchase-receive") },
        body: JSON.stringify({ version: selected.version }),
      });
      setNotice("تم استلام جميع بنود الأمر وتحديث المخزون واعتماد فاتورة المشتريات تلقائيًا.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر استلام أمر الشراء");
    } finally {
      setSubmitting(false);
    }
  }

  const setupReady = options.suppliers.length > 0 && options.warehouses.length > 0 && options.products.length > 0;

  return (
    <AppShell>
      <section className="page-heading purchase-heading">
        <div><h2>المشتريات</h2><p>احفظ الأمر كمسودة، ثم استلمه لتحديث المخزون وإنشاء فاتورة المورد.</p></div>
        <div className="page-heading__actions">
          {canManage ? <button className="secondary-button" onClick={() => { setShowCreate(true); window.requestAnimationFrame(() => createRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })); }}><Plus size={17} /> أمر شراء جديد</button> : null}
          <button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17} /> تحديث</button>
        </div>
      </section>
      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      {canManage && showCreate ? <section ref={createRef} className="panel master-form-card purchase-create-card">
        <header className="panel__head"><div><h3>أمر شراء جديد</h3><p>نفس بيانات أمر الشراء في نسخة الديسكتوب</p></div><button type="button" className="mini-action" aria-label="إغلاق" onClick={() => setShowCreate(false)}><X size={17} /></button></header>
        {setupReady ? <form className="compact-form purchase-form" onSubmit={submitOrder}>
          <div className="form-pair"><label>المورد<select value={supplierId} onChange={(event) => setSupplierId(event.target.value)} required>{options.suppliers.map((item) => <option key={item.id} value={item.id}>{item.name_ar} · {item.code}</option>)}</select></label><label>المخزن<input value={options.warehouses[0]?.name_ar ?? "المصنع"} disabled /></label></div>
          <div className="purchase-lines-head"><strong>بنود أمر الشراء</strong><button type="button" className="text-button" onClick={() => setDraftLines((current) => [...current, newDraftLine(options.products[0]?.id || "")])}><Plus size={15} /> إضافة بند</button></div>
          <div className="purchase-draft-lines">{draftLines.map((line, index) => {
            const product = options.products.find((item) => item.id === line.product_id);
            const gross = Number(line.quantity || 0);
            const loss = Number(line.purchase_loss || 0);
            const net = Math.max(0, gross - loss);
            const inventoryTotal = gross * (Number(line.unit_price || 0) + Number(line.internal_unit_cost || 0));
            const inventoryUnitCost = net > 0 ? inventoryTotal / net : 0;
            return <div className="purchase-draft-line" key={line.key}>
              <span className="purchase-line-number">{index + 1}</span>
              <label>الصنف<select value={line.product_id} onChange={(event) => updateDraftLine(line.key, { product_id: event.target.value, purchase_loss: defaultLoss(line.quantity, options.products.find((item) => item.id === event.target.value)) })} required>{options.products.map((item) => <option key={item.id} value={item.id}>{item.name_ar} · {item.code}</option>)}</select></label>
              <div className="form-pair"><label>إجمالي الكمية<input type="number" min="0.000001" step="0.001" value={line.quantity} onChange={(event) => updateQuantity(line, event.target.value)} required /></label><label>الوحدة<input value={product?.unit_symbol ?? ""} disabled /></label></div>
              <div className="form-pair"><label>سعر شراء المورد<input type="number" min="0" step="0.01" value={line.unit_price} onChange={(event) => updateDraftLine(line.key, { unit_price: event.target.value })} required /></label><label>تجهيز داخلي/وحدة<input type="number" min="0" step="0.01" value={line.internal_unit_cost} onChange={(event) => updateDraftLine(line.key, { internal_unit_cost: event.target.value })} /></label></div>
              <div className="form-pair"><label>فقد الشراء<input type="number" min="0" max={line.quantity || undefined} step="0.001" value={line.purchase_loss} onChange={(event) => updateDraftLine(line.key, { purchase_loss: event.target.value })} required /></label><label>صافي المخزن<input value={number.format(net)} disabled /></label></div>
              <div className="purchase-line-cost"><small>تكلفة المخزون/وحدة</small><strong>{currency.format(inventoryUnitCost)} ج.م</strong><small>مستحق المورد</small><strong>{currency.format(gross * Number(line.unit_price || 0))} ج.م</strong></div>
              {draftLines.length > 1 ? <button type="button" className="mini-action purchase-line-delete" aria-label="حذف البند" onClick={() => setDraftLines((current) => current.filter((item) => item.key !== line.key))}><Trash2 size={15} /></button> : null}
            </div>;
          })}</div>
          <label>ملاحظات<textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="ملاحظات أمر الشراء" /></label>
          <div className="purchase-form-total"><span>إجمالي مستحق المورد</span><strong>{currency.format(draftTotal)} ج.م</strong></div>
          <button className="primary-button" disabled={submitting}><FilePlus2 size={17} /> حفظ أمر الشراء كمسودة</button>
        </form> : <div className="setup-note"><PackageCheck size={20} /><div><strong>أكمل البيانات الأساسية أولًا</strong><p>يلزم وجود مورد وصنف ومخزن مصنع نشط.</p></div></div>}
      </section> : null}

      <section className="panel purchase-orders-panel">
        <header className="panel__head"><div><h3>أوامر الشراء</h3><p>اختر أمرًا لعرض تفاصيله</p></div><span className="status-badge status-badge--active">{orders.length} أمر</span></header>
        {orders.length ? <div className="purchase-order-list">{orders.map((item) => {
          const meta = statusMeta[item.status];
          return <button type="button" key={item.id} className={`purchase-order-card ${selectedId === item.id ? "purchase-order-card--selected" : ""}`} onClick={() => selectOrder(item.id)}><span className="purchase-order-card__icon"><PackageCheck size={19} /></span><span><strong dir="ltr">{item.order_number}</strong><small>{item.supplier_name_ar} · {item.lines.length} بند</small></span><span className={`purchase-status ${meta.className}`}>{meta.label}</span><span className="purchase-order-card__value">{currency.format(Number(item.total))} ج.م</span></button>;
        })}</div> : <div className="empty-state"><span className="empty-state__icon"><PackageCheck size={27} /></span><h4>لا توجد أوامر شراء</h4><p>أنشئ أول أمر شراء.</p></div>}
      </section>

      {selected ? <section ref={detailRef} className="panel purchase-detail">
        <header className="panel__head"><div><h3>تفاصيل {selected.order_number}</h3><p>{selected.supplier_name_ar} · {selected.warehouse_name_ar} · {new Date(selected.order_date).toLocaleString("ar-EG")}</p></div><span className={`purchase-status ${statusMeta[selected.status].className}`}>{statusMeta[selected.status].label}</span></header>
        <div className="data-table-wrap"><table className="data-table purchase-lines-table"><thead><tr><th>الكود</th><th>الصنف</th><th>الدفعة</th><th>إجمالي الكمية</th><th>سعر المورد</th><th>تجهيز داخلي</th><th>الفقد</th><th>صافي المخزن</th><th>تكلفة المخزون</th><th>مستحق المورد</th></tr></thead><tbody>{selected.lines.map((line) => <tr key={line.id}><td dir="ltr">{line.product_code}</td><td>{line.product_name_ar}</td><td dir="ltr">{line.lot_number}</td><td className="numeric-cell">{number.format(Number(line.ordered_quantity))}</td><td className="numeric-cell">{currency.format(Number(line.unit_price))}</td><td className="numeric-cell">{currency.format(Number(line.additional_unit_cost))}</td><td className="numeric-cell">{number.format(Number(line.purchase_loss_quantity))}</td><td className="numeric-cell">{number.format(Number(line.net_quantity))}</td><td className="numeric-cell">{currency.format(Number(line.inventory_unit_cost))}</td><td className="numeric-cell"><strong>{currency.format(Number(line.line_total))}</strong></td></tr>)}</tbody></table></div>
        {canManage && ["draft", "approved", "partially_received"].includes(selected.status) ? <div className="purchase-action-callout"><span><Truck size={22} /></span><div><strong>استلام الأمر المحدد</strong><p>يُضاف صافي جميع البنود للمخزون وتُعتمد فاتورة المورد تلقائيًا.</p></div><button className="primary-button" onClick={() => void receiveSelected()} disabled={submitting}><Truck size={17} /> استلام الأمر المحدد</button></div> : null}
        {selected.supplier_invoice ? <div className="invoice-chip"><ReceiptText size={18} /><span><strong>{selected.supplier_invoice.invoice_number}</strong><small>فاتورة مشتريات معتمدة تلقائيًا</small></span><strong>{currency.format(Number(selected.supplier_invoice.total))} ج.م</strong></div> : null}
        <footer className="purchase-detail-total"><span><Scale size={18} /> إجمالي مستحق المورد</span><strong>{currency.format(Number(selected.total))} ج.م</strong></footer>
      </section> : null}
    </AppShell>
  );
}
