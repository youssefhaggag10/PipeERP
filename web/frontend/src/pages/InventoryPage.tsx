import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Boxes,
  Check,
  Layers3,
  PackageSearch,
  RefreshCw,
  Repeat2,
  Scale,
  SlidersHorizontal,
  Undo2,
  Warehouse,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { clientId } from "../lib/clientId";

type InventoryOption = {
  id: string;
  code: string;
  name_ar: string;
};

type InventoryOptions = {
  products: InventoryOption[];
  warehouses: InventoryOption[];
};

type Balance = {
  product_id: string;
  warehouse_id: string;
  quantity_on_hand: string;
  weight_on_hand_kg: string;
  version: number;
  product_code: string;
  product_name_ar: string;
  warehouse_name_ar: string;
};

type Transaction = {
  id: string;
  transaction_type: "receipt" | "issue" | string;
  product_id: string;
  warehouse_id: string;
  quantity_delta: string;
  weight_delta_kg: string;
  unit_cost: string;
  total_cost: string;
  reference_type: string;
  reference_id: string | null;
  lot_number: string;
  product_code: string;
  product_name_ar: string;
  warehouse_name_ar: string;
  notes: string;
  cost_basis: CostBasis;
  reversal_of_id: string | null;
  posted_at: string;
};

type LotBalance = {
  lot_id: string;
  product_id: string;
  warehouse_id: string;
  product_code: string;
  product_name_ar: string;
  warehouse_name_ar: string;
  lot_number: string;
  received_at: string;
  quantity_received: string;
  quantity_issued: string;
  quantity_remaining: string;
  weight_received_kg: string;
  weight_issued_kg: string;
  weight_remaining_kg: string;
  average_cost: string;
  inventory_value: string;
};

type MovementType = "receipt" | "issue" | "transfer" | "adjustment";
type CostBasis = "quantity" | "weight";
type InventoryView = "balances" | "lots" | "stock-card";

const numberFormat = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 3 });
const moneyFormat = new Intl.NumberFormat("ar-EG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatNumber(value: string | number) {
  return numberFormat.format(Number(value));
}

function freshKey() {
  return clientId("inventory");
}

const movementLabels: Record<string, string> = {
  receipt: "استلام",
  issue: "صرف",
  transfer_in: "تحويل وارد",
  transfer_out: "تحويل صادر",
  adjustment_in: "تسوية زيادة",
  adjustment_out: "تسوية خفض",
  reversal_in: "عكس وارد",
  reversal_out: "عكس صادر",
};

function isInbound(transaction: Transaction) {
  return Number(transaction.quantity_delta) > 0 || Number(transaction.weight_delta_kg) > 0;
}

function canReverse(transaction: Transaction) {
  return (
    transaction.reversal_of_id === null &&
    ["receipt", "issue", "adjustment_in", "adjustment_out"].includes(transaction.transaction_type)
  );
}

export function InventoryPage() {
  const { user } = useAuth();
  const location = useLocation();
  const canManage = user?.permissions.includes("inventory.manage") ?? false;
  const requestedView = new URLSearchParams(location.search).get("view");
  const [balances, setBalances] = useState<Balance[]>([]);
  const [lotBalances, setLotBalances] = useState<LotBalance[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [options, setOptions] = useState<InventoryOptions>({ products: [], warehouses: [] });
  const [movementType, setMovementType] = useState<MovementType>("receipt");
  const [productId, setProductId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [destinationWarehouseId, setDestinationWarehouseId] = useState("");
  const [costBasis, setCostBasis] = useState<CostBasis>("quantity");
  const [adjustmentDirection, setAdjustmentDirection] = useState<"increase" | "decrease">("increase");
  const [quantity, setQuantity] = useState("");
  const [weight, setWeight] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [lotNumber, setLotNumber] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reversalTarget, setReversalTarget] = useState<Transaction | null>(null);
  const [reversalReason, setReversalReason] = useState("");
  const [inventoryView, setInventoryView] = useState<InventoryView>(requestedView === "stock-card" ? "stock-card" : "balances");
  const [stockCardProductId, setStockCardProductId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [balanceRows, lotRows, transactionRows, optionRows] = await Promise.all([
        api<Balance[]>("/inventory/balances"),
        api<LotBalance[]>("/inventory/lot-balances"),
        api<Transaction[]>("/inventory/transactions?limit=500"),
        api<InventoryOptions>("/inventory/options"),
      ]);
      setBalances(balanceRows);
      setLotBalances(lotRows);
      setTransactions(transactionRows);
      setOptions(optionRows);
      setProductId((current) => current || optionRows.products[0]?.id || "");
      setStockCardProductId((current) => current || optionRows.products[0]?.id || "");
      setWarehouseId((current) => current || optionRows.warehouses[0]?.id || "");
      setDestinationWarehouseId((current) => {
        if (current && current !== (warehouseId || optionRows.warehouses[0]?.id)) return current;
        return optionRows.warehouses.find((item) => item.id !== (warehouseId || optionRows.warehouses[0]?.id))?.id || "";
      });
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل بيانات المخزون");
    } finally {
      setLoading(false);
    }
  }, [warehouseId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (requestedView === "stock-card") setInventoryView("stock-card");
  }, [requestedView]);

  const totals = useMemo(
    () => ({
      products: new Set(balances.filter((item) => Number(item.quantity_on_hand) || Number(item.weight_on_hand_kg)).map((item) => item.product_id)).size,
      quantity: balances.reduce((sum, item) => sum + Number(item.quantity_on_hand), 0),
      weight: balances.reduce((sum, item) => sum + Number(item.weight_on_hand_kg), 0),
    }),
    [balances],
  );
  const stockCardRows = useMemo(
    () => transactions.filter((item) => !stockCardProductId || item.product_id === stockCardProductId),
    [stockCardProductId, transactions],
  );

  function changeMovementType(value: MovementType) {
    setMovementType(value);
    setError("");
    setNotice("");
    setQuantity("");
    setWeight("");
  }

  async function submitMovement(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setSubmitting(true);
    try {
      const isReceipt = movementType === "receipt";
      const isTransfer = movementType === "transfer";
      const isAdjustment = movementType === "adjustment";
      const amount = costBasis === "quantity" ? quantity : weight;
      const payload = isTransfer
        ? {
            product_id: productId,
            source_warehouse_id: warehouseId,
            destination_warehouse_id: destinationWarehouseId,
            amount,
            cost_basis: costBasis,
            notes,
          }
        : isAdjustment
          ? {
              product_id: productId,
              warehouse_id: warehouseId,
              direction: adjustmentDirection,
              quantity: quantity || "0",
              weight_kg: weight || "0",
              cost_basis: costBasis,
              unit_cost: unitCost || "0",
              reason: notes,
            }
        : isReceipt
        ? {
            product_id: productId,
            warehouse_id: warehouseId,
            quantity: quantity || "0",
            weight_kg: weight || "0",
            cost_basis: costBasis,
            unit_cost: unitCost || "0",
            lot_number: lotNumber,
            reference_type: "manual_receipt",
            notes,
          }
        : {
            product_id: productId,
            warehouse_id: warehouseId,
            amount,
            cost_basis: costBasis,
            reference_type: "manual_issue",
            notes,
          };
      await api<Transaction>(
        `/inventory/${isTransfer ? "transfers" : isAdjustment ? "adjustments" : isReceipt ? "receipts" : "issues"}`,
        {
        method: "POST",
        headers: { "Idempotency-Key": freshKey() },
        body: JSON.stringify(payload),
        },
      );
      setQuantity("");
      setWeight("");
      setUnitCost("");
      setLotNumber("");
      setNotes("");
      setNotice(
        isTransfer
          ? "تم التحويل ذريًا بين المخزنين مع الحفاظ على قيمة تكلفة FIFO."
          : isAdjustment
            ? "تم ترحيل التسوية وتسجيل سببها في سجل التدقيق."
          : isReceipt
            ? "تم ترحيل الاستلام وتكوين طبقة FIFO جديدة."
            : "تم ترحيل الصرف وتخصيص التكلفة من أقدم الطبقات.",
      );
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر ترحيل حركة المخزون");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitReversal(event: FormEvent) {
    event.preventDefault();
    if (!reversalTarget) return;
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await api<Transaction>(`/inventory/transactions/${reversalTarget.id}/reversal`, {
        method: "POST",
        headers: { "Idempotency-Key": freshKey() },
        body: JSON.stringify({ reason: reversalReason }),
      });
      setReversalTarget(null);
      setReversalReason("");
      setNotice("تم إنشاء حركة عكسية مرتبطة بالأصل دون تعديل السجل التاريخي.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر عكس حركة المخزون");
    } finally {
      setSubmitting(false);
    }
  }

  const hasSetup = options.products.length > 0 && options.warehouses.length > 0;

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <span className="eyebrow">المرحلة الرابعة · دورة المخزون</span>
          <h2>المخزون وطبقات FIFO</h2>
          <p>أرصدة لحظية وحركات غير قابلة للتعديل مع تكلفة دقيقة بالكمية أو الوزن.</p>
        </div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={17} /> تحديث البيانات
        </button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      <section className="inventory-stats" aria-label="ملخص المخزون">
        <article><span className="inventory-stat__icon"><PackageSearch size={21} /></span><span><small>أصناف لها رصيد</small><strong>{totals.products}</strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--blue"><Boxes size={21} /></span><span><small>إجمالي الكمية</small><strong>{formatNumber(totals.quantity)}</strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--amber"><Scale size={21} /></span><span><small>إجمالي الوزن</small><strong>{formatNumber(totals.weight)} <em>كجم</em></strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--violet"><Layers3 size={21} /></span><span><small>آخر الحركات</small><strong>{transactions.length}</strong></span></article>
      </section>

      <div className="sales-tabs inventory-view-tabs" role="tablist" aria-label="تقارير المخزون">
        <button className={inventoryView === "balances" ? "active" : ""} onClick={() => setInventoryView("balances")}><Boxes size={17} /> الأرصدة الحالية</button>
        <button className={inventoryView === "lots" ? "active" : ""} onClick={() => setInventoryView("lots")}><Layers3 size={17} /> أرصدة التشغيلات</button>
        <button className={inventoryView === "stock-card" ? "active" : ""} onClick={() => setInventoryView("stock-card")}><PackageSearch size={17} /> كارت الصنف</button>
      </div>

      <section className={`master-layout inventory-layout ${canManage ? "" : "master-layout--single"}`}>
        <article className="panel">
          <header className="panel__head"><div><h3>{inventoryView === "balances" ? "الأرصدة الحالية" : inventoryView === "lots" ? "أرصدة التشغيلات" : "كارت الصنف"}</h3><p>{inventoryView === "balances" ? "الرصيد المجمع حسب الصنف والمخزن" : inventoryView === "lots" ? "المتبقي والقيمة لكل تشغيلة وفق FIFO" : "كل حركات الصنف داخل وخارج بالمخزن والتشغيلة والمرجع"}</p></div><span className="status-badge status-badge--active">محدّث</span></header>
          {inventoryView === "balances" && balances.length ? (
            <div className="data-table-wrap">
              <table className="data-table inventory-table">
                <thead><tr><th>الصنف</th><th>المخزن</th><th>الكمية</th><th>الوزن</th><th>حالة الرصيد</th></tr></thead>
                <tbody>{balances.map((item) => {
                  const empty = Number(item.quantity_on_hand) === 0 && Number(item.weight_on_hand_kg) === 0;
                  return <tr key={`${item.product_id}-${item.warehouse_id}`}><td><strong>{item.product_name_ar}</strong><small dir="ltr">{item.product_code}</small></td><td><Warehouse size={14} /> {item.warehouse_name_ar}</td><td className="numeric-cell">{formatNumber(item.quantity_on_hand)}</td><td className="numeric-cell">{formatNumber(item.weight_on_hand_kg)} كجم</td><td><span className={`status-badge ${empty ? "" : "status-badge--active"}`}>{empty ? "بدون رصيد" : "متاح"}</span></td></tr>;
                })}</tbody>
              </table>
            </div>
          ) : inventoryView === "lots" && lotBalances.length ? <div className="data-table-wrap"><table className="data-table inventory-table"><thead><tr><th>الصنف</th><th>المخزن</th><th>التشغيلة</th><th>تاريخ الاستلام</th><th>المستلم</th><th>المصروف</th><th>المتبقي</th><th>متوسط التكلفة</th><th>القيمة</th></tr></thead><tbody>{lotBalances.map((item) => <tr key={item.lot_id}><td><strong>{item.product_name_ar}</strong><small dir="ltr">{item.product_code}</small></td><td>{item.warehouse_name_ar}</td><td dir="ltr">{item.lot_number}</td><td>{new Date(item.received_at).toLocaleDateString("ar-EG")}</td><td className="numeric-cell">{formatNumber(item.quantity_received)} / {formatNumber(item.weight_received_kg)} كجم</td><td className="numeric-cell">{formatNumber(item.quantity_issued)} / {formatNumber(item.weight_issued_kg)} كجم</td><td className="numeric-cell"><strong>{formatNumber(item.quantity_remaining)} / {formatNumber(item.weight_remaining_kg)} كجم</strong></td><td className="numeric-cell">{moneyFormat.format(Number(item.average_cost))}</td><td className="numeric-cell"><strong>{moneyFormat.format(Number(item.inventory_value))}</strong></td></tr>)}</tbody></table></div> : inventoryView === "stock-card" ? <><label className="stock-card-filter">الصنف<select value={stockCardProductId} onChange={(event) => setStockCardProductId(event.target.value)}>{options.products.map((item) => <option key={item.id} value={item.id}>{item.name_ar} · {item.code}</option>)}</select></label>{stockCardRows.length ? <div className="data-table-wrap"><table className="data-table inventory-table"><thead><tr><th>التاريخ</th><th>المخزن</th><th>التشغيلة</th><th>داخل</th><th>خارج</th><th>الوزن</th><th>تكلفة الوحدة</th><th>القيمة</th><th>المرجع</th></tr></thead><tbody>{stockCardRows.map((item) => { const inbound = isInbound(item); return <tr key={item.id}><td>{new Intl.DateTimeFormat("ar-EG", { dateStyle: "short", timeStyle: "short" }).format(new Date(item.posted_at))}</td><td>{item.warehouse_name_ar}</td><td dir="ltr">{item.lot_number || "—"}</td><td className="numeric-cell movement-positive">{inbound ? formatNumber(Math.max(0, Number(item.quantity_delta))) : "—"}</td><td className="numeric-cell movement-negative">{!inbound ? formatNumber(Math.abs(Number(item.quantity_delta))) : "—"}</td><td className="numeric-cell">{formatNumber(item.weight_delta_kg)} كجم</td><td className="numeric-cell">{moneyFormat.format(Number(item.unit_cost))}</td><td className="numeric-cell">{moneyFormat.format(Number(item.total_cost))}</td><td><strong>{movementLabels[item.transaction_type] ?? item.reference_type}</strong><small dir="ltr">{item.reference_id || "—"}</small></td></tr>; })}</tbody></table></div> : <div className="empty-state"><PackageSearch size={27} /><h4>لا توجد حركات لهذا الصنف</h4></div>}</> : <div className="empty-state"><span className="empty-state__icon"><Boxes size={27} /></span><h4>{inventoryView === "lots" ? "لا توجد تشغيلات حتى الآن" : "لا توجد أرصدة حتى الآن"}</h4><p>رحّل أول حركة استلام لتكوين الرصيد وطبقة تكلفة FIFO.</p></div>}
        </article>

        {canManage ? (
          <article className="panel master-form-card inventory-movement-card">
            <header className="panel__head"><div><h3>ترحيل حركة مخزون</h3><p>كل عملية تحفظ كسجل مستقل قابل للتدقيق</p></div></header>
            <div className="movement-switch movement-switch--four" role="tablist" aria-label="نوع الحركة">
              <button type="button" role="tab" aria-selected={movementType === "receipt"} className={movementType === "receipt" ? "movement-switch--active" : ""} onClick={() => changeMovementType("receipt")}><ArrowDownToLine size={17} /> استلام</button>
              <button type="button" role="tab" aria-selected={movementType === "issue"} className={movementType === "issue" ? "movement-switch--active movement-switch--issue" : ""} onClick={() => changeMovementType("issue")}><ArrowUpFromLine size={17} /> صرف</button>
              <button type="button" role="tab" aria-selected={movementType === "transfer"} className={movementType === "transfer" ? "movement-switch--active movement-switch--transfer" : ""} onClick={() => changeMovementType("transfer")}><Repeat2 size={17} /> تحويل</button>
              <button type="button" role="tab" aria-selected={movementType === "adjustment"} className={movementType === "adjustment" ? "movement-switch--active movement-switch--adjustment" : ""} onClick={() => changeMovementType("adjustment")}><SlidersHorizontal size={17} /> تسوية</button>
            </div>
            {hasSetup ? <form className="compact-form inventory-form" onSubmit={submitMovement}>
              <label>الصنف<select value={productId} onChange={(event) => setProductId(event.target.value)} required>{options.products.map((item) => <option value={item.id} key={item.id}>{item.name_ar} · {item.code}</option>)}</select></label>
              <label>{movementType === "transfer" ? "من مخزن" : "المخزن"}<select value={warehouseId} onChange={(event) => { const value = event.target.value; setWarehouseId(value); if (value === destinationWarehouseId) setDestinationWarehouseId(options.warehouses.find((item) => item.id !== value)?.id || ""); }} required>{options.warehouses.map((item) => <option value={item.id} key={item.id}>{item.name_ar} · {item.code}</option>)}</select></label>
              {movementType === "transfer" ? <label>إلى مخزن<select value={destinationWarehouseId} onChange={(event) => setDestinationWarehouseId(event.target.value)} required>{options.warehouses.filter((item) => item.id !== warehouseId).map((item) => <option value={item.id} key={item.id}>{item.name_ar} · {item.code}</option>)}</select></label> : null}
              {movementType === "adjustment" ? <label>اتجاه التسوية<select value={adjustmentDirection} onChange={(event) => setAdjustmentDirection(event.target.value as "increase" | "decrease")}><option value="increase">زيادة الرصيد</option><option value="decrease">خفض الرصيد</option></select></label> : null}
              <fieldset className="basis-picker"><legend>أساس التكلفة والصرف</legend><label><input type="radio" name="basis" value="quantity" checked={costBasis === "quantity"} onChange={() => setCostBasis("quantity")} /> بالكمية</label><label><input type="radio" name="basis" value="weight" checked={costBasis === "weight"} onChange={() => setCostBasis("weight")} /> بالوزن</label></fieldset>
              <div className="form-pair">
                <label>الكمية<input type="number" min="0" step="0.000001" value={quantity} onChange={(event) => setQuantity(event.target.value)} required={(movementType !== "receipt" && movementType !== "adjustment" || movementType === "adjustment" && adjustmentDirection === "decrease") && costBasis === "quantity"} disabled={(movementType !== "receipt" && movementType !== "adjustment" || movementType === "adjustment" && adjustmentDirection === "decrease") && costBasis === "weight"} /></label>
                <label>الوزن بالكيلو<input type="number" min="0" step="0.000001" value={weight} onChange={(event) => setWeight(event.target.value)} required={(movementType !== "receipt" && movementType !== "adjustment" || movementType === "adjustment" && adjustmentDirection === "decrease") && costBasis === "weight"} disabled={(movementType !== "receipt" && movementType !== "adjustment" || movementType === "adjustment" && adjustmentDirection === "decrease") && costBasis === "quantity"} /></label>
              </div>
              {movementType === "receipt" || movementType === "adjustment" && adjustmentDirection === "increase" ? <label>تكلفة الوحدة<input type="number" min="0" step="0.000001" value={unitCost} onChange={(event) => setUnitCost(event.target.value)} required /></label> : null}
              {movementType === "receipt" ? <label>رقم التشغيلة <small>(اختياري)</small><input dir="ltr" value={lotNumber} onChange={(event) => setLotNumber(event.target.value)} maxLength={80} placeholder="LOT-2026-001" /></label> : null}
              <label>{movementType === "adjustment" ? "سبب التسوية" : "ملاحظات"}<textarea value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} minLength={movementType === "adjustment" ? 3 : undefined} required={movementType === "adjustment"} rows={3} placeholder={movementType === "adjustment" ? "مثال: فرق نتيجة الجرد الفعلي..." : "سبب الحركة أو مرجع داخلي..."} /></label>
              <button className={`primary-button ${movementType === "issue" || movementType === "adjustment" && adjustmentDirection === "decrease" ? "danger-button" : ""}`} disabled={submitting || (movementType === "transfer" && options.warehouses.length < 2)}>{movementType === "receipt" ? <ArrowDownToLine size={17} /> : movementType === "issue" ? <ArrowUpFromLine size={17} /> : movementType === "transfer" ? <Repeat2 size={17} /> : <SlidersHorizontal size={17} />}{submitting ? "جارٍ الترحيل..." : movementType === "receipt" ? "ترحيل الاستلام" : movementType === "issue" ? "ترحيل الصرف" : movementType === "transfer" ? "تنفيذ التحويل" : "ترحيل التسوية"}</button>
            </form> : <div className="setup-note"><Warehouse size={22} /><div><strong>أكمل البيانات الأساسية أولًا</strong><p>يلزم وجود منتج مخزني ومخزن نشط قبل تسجيل الحركة.</p></div></div>}
          </article>
        ) : null}
      </section>

      <section className="panel inventory-history">
        <header className="panel__head"><div><h3>سجل الحركات</h3><p>أحدث 500 حركة مع التكلفة والمرجع والتوقيت</p></div></header>
        {reversalTarget ? <form className="reversal-bar" onSubmit={submitReversal}><Undo2 size={20} /><div><strong>عكس حركة {movementLabels[reversalTarget.transaction_type] ?? reversalTarget.transaction_type}</strong><small>{reversalTarget.product_name_ar} · {reversalTarget.warehouse_name_ar}</small></div><input value={reversalReason} onChange={(event) => setReversalReason(event.target.value)} minLength={3} maxLength={500} placeholder="اكتب سبب العكس..." required /><button className="danger-button secondary-button" disabled={submitting}><Undo2 size={15} /> تأكيد العكس</button><button type="button" className="secondary-button" onClick={() => { setReversalTarget(null); setReversalReason(""); }}>إلغاء</button></form> : null}
        {transactions.length ? <div className="data-table-wrap"><table className="data-table inventory-table"><thead><tr><th>الحركة</th><th>الصنف</th><th>المخزن</th><th>الكمية</th><th>الوزن</th><th>التكلفة</th><th>التوقيت</th>{canManage ? <th>إجراء</th> : null}</tr></thead><tbody>{transactions.map((item) => { const inbound = isInbound(item); return <tr key={item.id}><td><span className={`movement-badge ${inbound ? "movement-badge--receipt" : "movement-badge--issue"}`}>{inbound ? <ArrowDownToLine size={13} /> : <ArrowUpFromLine size={13} />}{movementLabels[item.transaction_type] ?? item.transaction_type}</span>{item.reversal_of_id ? <small>حركة عكسية</small> : null}</td><td><strong>{item.product_name_ar}</strong><small dir="ltr">{item.product_code}</small></td><td>{item.warehouse_name_ar}</td><td className={`numeric-cell ${inbound ? "movement-positive" : "movement-negative"}`}>{formatNumber(item.quantity_delta)}</td><td className={`numeric-cell ${inbound ? "movement-positive" : "movement-negative"}`}>{formatNumber(item.weight_delta_kg)} كجم</td><td className="numeric-cell">{moneyFormat.format(Number(item.total_cost))}</td><td><time dateTime={item.posted_at}>{new Intl.DateTimeFormat("ar-EG", { dateStyle: "short", timeStyle: "short" }).format(new Date(item.posted_at))}</time></td>{canManage ? <td>{canReverse(item) ? <button className="mini-action" onClick={() => { setReversalTarget(item); setReversalReason(""); }}><Undo2 size={14} /> عكس</button> : <span className="muted-action">—</span>}</td> : null}</tr>; })}</tbody></table></div> : <div className="empty-state"><span className="empty-state__icon"><Layers3 size={27} /></span><h4>سجل الحركات فارغ</h4><p>ستظهر هنا كل حركة استلام أو صرف فور ترحيلها.</p></div>}
      </section>
    </AppShell>
  );
}
