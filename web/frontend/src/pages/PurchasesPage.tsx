import {
  BadgeCheck,
  Banknote,
  Check,
  ClipboardCheck,
  FilePlus2,
  PackageCheck,
  Plus,
  ReceiptText,
  RefreshCw,
  Scale,
  ShoppingBag,
  Trash2,
  Truck,
  Undo2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type CostBasis = "quantity" | "weight";
type OrderStatus = "draft" | "approved" | "partially_received" | "received" | "cancelled";
type PaymentMethod = "cash" | "bank_transfer" | "cheque" | "wallet";

type Option = { id: string; code: string; name_ar: string; account_type: string };
type PurchaseOptions = { suppliers: Option[]; warehouses: Option[]; products: Option[]; financial_accounts: Option[] };

type OrderLine = {
  id: string;
  product_id: string;
  product_code: string;
  product_name_ar: string;
  cost_basis: CostBasis;
  ordered_quantity: string;
  ordered_weight_kg: string;
  received_quantity: string;
  received_weight_kg: string;
  unit_price: string;
  additional_unit_cost: string;
  line_total: string;
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
};

type DraftLine = {
  key: string;
  product_id: string;
  cost_basis: CostBasis;
  ordered_quantity: string;
  ordered_weight_kg: string;
  unit_price: string;
  additional_unit_cost: string;
};

type ReceiptDraft = {
  gross_quantity: string;
  gross_weight_kg: string;
  loss_quantity: string;
  loss_weight_kg: string;
  lot_number: string;
};

type PurchaseReceipt = {
  id: string;
  receipt_number: string;
  status: "posted" | "reversed";
  notes: string;
  posted_at: string;
  reversed_at: string | null;
  reversal_reason: string;
  lines: Array<{
    id: string;
    product_name_ar: string;
    net_quantity: string;
    net_weight_kg: string;
    capitalized_cost: string;
  }>;
};

const currency = new Intl.NumberFormat("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const number = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 3 });

const statusMeta: Record<OrderStatus, { label: string; className: string }> = {
  draft: { label: "مسودة", className: "purchase-status--draft" },
  approved: { label: "معتمد", className: "purchase-status--approved" },
  partially_received: { label: "استلام جزئي", className: "purchase-status--partial" },
  received: { label: "مستلم بالكامل", className: "purchase-status--received" },
  cancelled: { label: "ملغي", className: "purchase-status--cancelled" },
};

function newDraftLine(): DraftLine {
  return {
    key: crypto.randomUUID(),
    product_id: "",
    cost_basis: "quantity",
    ordered_quantity: "",
    ordered_weight_kg: "",
    unit_price: "",
    additional_unit_cost: "",
  };
}

function freshKey() {
  return `purchase-${crypto.randomUUID()}`;
}

export function PurchasesPage() {
  const { user } = useAuth();
  const canManage = user?.permissions.includes("purchases.manage") ?? false;
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [options, setOptions] = useState<PurchaseOptions>({ suppliers: [], warehouses: [], products: [], financial_accounts: [] });
  const [selectedId, setSelectedId] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [notes, setNotes] = useState("");
  const [advanceEnabled, setAdvanceEnabled] = useState(false);
  const [advanceAmount, setAdvanceAmount] = useState("");
  const [advanceMethod, setAdvanceMethod] = useState<PaymentMethod>("cash");
  const [advanceAccountId, setAdvanceAccountId] = useState("");
  const [draftLines, setDraftLines] = useState<DraftLine[]>([newDraftLine()]);
  const [receiptDrafts, setReceiptDrafts] = useState<Record<string, ReceiptDraft>>({});
  const [receipts, setReceipts] = useState<PurchaseReceipt[]>([]);
  const [receiptNotes, setReceiptNotes] = useState("");
  const [reversalTargetId, setReversalTargetId] = useState("");
  const [reversalReason, setReversalReason] = useState("");
  const [supplierInvoiceNumber, setSupplierInvoiceNumber] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [orderRows, optionRows] = await Promise.all([
        api<PurchaseOrder[]>("/purchases/orders?limit=150"),
        api<PurchaseOptions>("/purchases/options"),
      ]);
      setOrders(orderRows);
      setOptions(optionRows);
      setSelectedId((current) => current || orderRows[0]?.id || "");
      setSupplierId((current) => current || optionRows.suppliers[0]?.id || "");
      setWarehouseId((current) => current || optionRows.warehouses[0]?.id || "");
      setAdvanceAccountId((current) => current || optionRows.financial_accounts.find((item) => item.account_type === "cash")?.id || "");
      setDraftLines((current) => current.map((line) => ({
        ...line,
        product_id: line.product_id || optionRows.products[0]?.id || "",
      })));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل دورة المشتريات");
    } finally {
      setLoading(false);
    }
  }, []);

  const advanceAccountType = { cash: "cash", bank_transfer: "bank", cheque: "bank", wallet: "wallet" }[advanceMethod];
  const advanceAccounts = useMemo(() => options.financial_accounts.filter((item) => item.account_type === advanceAccountType), [advanceAccountType, options.financial_accounts]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!advanceAccounts.some((item) => item.id === advanceAccountId)) {
      setAdvanceAccountId(advanceAccounts[0]?.id || "");
    }
  }, [advanceAccountId, advanceAccounts]);

  useEffect(() => {
    if (!selectedId) {
      setReceipts([]);
      return;
    }
    void api<PurchaseReceipt[]>(`/purchases/orders/${selectedId}/receipts`)
      .then(setReceipts)
      .catch((reason: unknown) => {
        setError(reason instanceof ApiError ? reason.message : "تعذر تحميل سندات الاستلام");
      });
  }, [selectedId]);

  const selected = orders.find((item) => item.id === selectedId) ?? null;
  const stats = useMemo(() => ({
    open: orders.filter((item) => ["draft", "approved", "partially_received"].includes(item.status)).length,
    partial: orders.filter((item) => item.status === "partially_received").length,
    received: orders.filter((item) => item.status === "received").length,
    value: orders.reduce((sum, item) => sum + Number(item.total), 0),
  }), [orders]);

  function updateDraftLine(key: string, patch: Partial<DraftLine>) {
    setDraftLines((current) => current.map((line) => line.key === key ? { ...line, ...patch } : line));
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
          warehouse_id: warehouseId,
          notes,
          advance_amount: advanceEnabled ? advanceAmount : "0",
          advance_payment_method: advanceMethod,
          advance_financial_account_id: advanceEnabled ? advanceAccountId : null,
          lines: draftLines.map((line) => ({
            product_id: line.product_id,
            cost_basis: line.cost_basis,
            ordered_quantity: line.ordered_quantity || "0",
            ordered_weight_kg: line.ordered_weight_kg || "0",
            unit_price: line.unit_price,
            additional_unit_cost: line.additional_unit_cost || "0",
          })),
        }),
      });
      setNotes("");
      setAdvanceEnabled(false);
      setAdvanceAmount("");
      setDraftLines([{ ...newDraftLine(), product_id: options.products[0]?.id || "" }]);
      setNotice(`تم إنشاء أمر الشراء ${created.order_number} كمسودة جاهزة للمراجعة.`);
      setSelectedId(created.id);
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء أمر الشراء");
    } finally {
      setSubmitting(false);
    }
  }

  async function approveSelected() {
    if (!selected) return;
    setSubmitting(true);
    setError("");
    try {
      await api(`/purchases/orders/${selected.id}/approval`, {
        method: "POST",
        body: JSON.stringify({ version: selected.version }),
      });
      setNotice(`تم اعتماد ${selected.order_number} ويمكن الآن تسجيل الاستلام.`);
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر اعتماد أمر الشراء");
    } finally {
      setSubmitting(false);
    }
  }

  function receiptValue(line: OrderLine): ReceiptDraft {
    return receiptDrafts[line.id] ?? {
      gross_quantity: "",
      gross_weight_kg: "",
      loss_quantity: "",
      loss_weight_kg: "",
      lot_number: "",
    };
  }

  function updateReceipt(lineId: string, patch: Partial<ReceiptDraft>) {
    const line = selected?.lines.find((item) => item.id === lineId);
    if (!line) return;
    setReceiptDrafts((current) => ({ ...current, [lineId]: { ...receiptValue(line), ...patch } }));
  }

  async function submitReceipt(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const lines = selected.lines
        .map((line) => ({ line, draft: receiptValue(line) }))
        .filter(({ draft }) => Number(draft.gross_quantity) > 0 || Number(draft.gross_weight_kg) > 0)
        .map(({ line, draft }) => ({
          purchase_order_line_id: line.id,
          gross_quantity: draft.gross_quantity || "0",
          gross_weight_kg: draft.gross_weight_kg || "0",
          loss_quantity: draft.loss_quantity || "0",
          loss_weight_kg: draft.loss_weight_kg || "0",
          lot_number: draft.lot_number,
        }));
      if (!lines.length) throw new ApiError("أدخل كمية استلام لبند واحد على الأقل", 422);
      await api(`/purchases/orders/${selected.id}/receipts`, {
        method: "POST",
        headers: { "Idempotency-Key": freshKey() },
        body: JSON.stringify({ notes: receiptNotes, lines }),
      });
      setReceiptDrafts({});
      setReceiptNotes("");
      setNotice("تم ترحيل الاستلام، وتحميل تكلفة الفاقد والمصاريف الإضافية على صافي طبقة FIFO.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر ترحيل الاستلام");
    } finally {
      setSubmitting(false);
    }
  }

  async function createInvoice(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSubmitting(true);
    setError("");
    try {
      await api(`/purchases/orders/${selected.id}/supplier-invoice`, {
        method: "POST",
        body: JSON.stringify({ supplier_invoice_number: supplierInvoiceNumber }),
      });
      setSupplierInvoiceNumber("");
      setNotice(`تم تسجيل فاتورة المورد المرتبطة بالأمر ${selected.order_number}.`);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تسجيل فاتورة المورد");
    } finally {
      setSubmitting(false);
    }
  }

  async function reverseReceipt(event: FormEvent) {
    event.preventDefault();
    if (!reversalTargetId || !selected) return;
    setSubmitting(true);
    setError("");
    try {
      await api(`/purchases/receipts/${reversalTargetId}/reversal`, {
        method: "POST",
        headers: { "Idempotency-Key": freshKey() },
        body: JSON.stringify({ reason: reversalReason }),
      });
      setReversalTargetId("");
      setReversalReason("");
      setNotice("تم عكس سند الاستلام وطبقة FIFO المرتبطة به وإعادة فتح أمر الشراء.");
      const [orderRows, receiptRows] = await Promise.all([
        api<PurchaseOrder[]>("/purchases/orders?limit=150"),
        api<PurchaseReceipt[]>(`/purchases/orders/${selected.id}/receipts`),
      ]);
      setOrders(orderRows);
      setReceipts(receiptRows);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر عكس سند الاستلام");
    } finally {
      setSubmitting(false);
    }
  }

  const setupReady = options.suppliers.length > 0 && options.warehouses.length > 0 && options.products.length > 0;

  return (
    <AppShell>
      <section className="page-heading purchase-heading">
        <div>
          <span className="eyebrow">المرحلة الخامسة · المشتريات والتكلفة</span>
          <h2>دورة الشراء والاستلام</h2>
          <p>أوامر متعددة البنود، استلامات جزئية، واحتساب دقيق للفاقد داخل تكلفة FIFO.</p>
        </div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={17} /> تحديث البيانات
        </button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      <section className="inventory-stats" aria-label="ملخص المشتريات">
        <article><span className="inventory-stat__icon"><ShoppingBag size={21} /></span><span><small>أوامر مفتوحة</small><strong>{stats.open}</strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--amber"><Truck size={21} /></span><span><small>استلام جزئي</small><strong>{stats.partial}</strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--blue"><ClipboardCheck size={21} /></span><span><small>مستلمة بالكامل</small><strong>{stats.received}</strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--violet"><Banknote size={21} /></span><span><small>إجمالي قيمة الأوامر</small><strong>{currency.format(stats.value)} <em>ج.م</em></strong></span></article>
      </section>

      <section className={`master-layout purchasing-layout ${canManage ? "" : "master-layout--single"}`}>
        <article className="panel purchase-orders-panel">
          <header className="panel__head"><div><h3>أوامر الشراء</h3><p>اختر أمرًا لعرض تفاصيله وتنفيذ الخطوة التالية</p></div><span className="status-badge status-badge--active">{orders.length} أمر</span></header>
          {orders.length ? <div className="purchase-order-list">{orders.map((item) => {
            const meta = statusMeta[item.status];
            return <button type="button" key={item.id} className={`purchase-order-card ${selectedId === item.id ? "purchase-order-card--selected" : ""}`} onClick={() => setSelectedId(item.id)}>
              <span className="purchase-order-card__icon"><PackageCheck size={19} /></span>
              <span><strong dir="ltr">{item.order_number}</strong><small>{item.supplier_name_ar} · {item.lines.length} بند</small></span>
              <span className={`purchase-status ${meta.className}`}>{meta.label}</span>
              <span className="purchase-order-card__value">{currency.format(Number(item.total))} ج.م</span>
            </button>;
          })}</div> : <div className="empty-state"><span className="empty-state__icon"><PackageCheck size={27} /></span><h4>لا توجد أوامر شراء</h4><p>أنشئ أول أمر متعدد البنود لبدء دورة التوريد.</p></div>}
        </article>

        {canManage ? <article className="panel master-form-card purchase-create-card">
          <header className="panel__head"><div><h3>أمر شراء جديد</h3><p>احفظه كمسودة ثم راجعه قبل الاعتماد</p></div><FilePlus2 size={20} /></header>
          {setupReady ? <form className="compact-form purchase-form" onSubmit={submitOrder}>
            <div className="form-pair">
              <label>المورد<select value={supplierId} onChange={(event) => setSupplierId(event.target.value)} required>{options.suppliers.map((item) => <option key={item.id} value={item.id}>{item.name_ar} · {item.code}</option>)}</select></label>
              <label>مخزن الاستلام<select value={warehouseId} onChange={(event) => setWarehouseId(event.target.value)} required>{options.warehouses.map((item) => <option key={item.id} value={item.id}>{item.name_ar}</option>)}</select></label>
            </div>
            <div className="purchase-lines-head"><strong>بنود الأمر</strong><button type="button" className="text-button" onClick={() => setDraftLines((current) => [...current, { ...newDraftLine(), product_id: options.products[0]?.id || "" }])}><Plus size={15} /> إضافة بند</button></div>
            <div className="purchase-draft-lines">{draftLines.map((line, index) => <div className="purchase-draft-line" key={line.key}>
              <span className="purchase-line-number">{index + 1}</span>
              <label>الصنف<select value={line.product_id} onChange={(event) => updateDraftLine(line.key, { product_id: event.target.value })} required>{options.products.map((item) => <option key={item.id} value={item.id}>{item.name_ar} · {item.code}</option>)}</select></label>
              <label>أساس التكلفة<select value={line.cost_basis} onChange={(event) => updateDraftLine(line.key, { cost_basis: event.target.value as CostBasis })}><option value="quantity">بالكمية</option><option value="weight">بالوزن</option></select></label>
              <div className="form-pair"><label>الكمية<input type="number" min="0" step="0.001" value={line.ordered_quantity} onChange={(event) => updateDraftLine(line.key, { ordered_quantity: event.target.value })} required={line.cost_basis === "quantity"} /></label><label>الوزن كجم<input type="number" min="0" step="0.001" value={line.ordered_weight_kg} onChange={(event) => updateDraftLine(line.key, { ordered_weight_kg: event.target.value })} required={line.cost_basis === "weight"} /></label></div>
              <div className="form-pair"><label>سعر الوحدة<input type="number" min="0" step="0.01" value={line.unit_price} onChange={(event) => updateDraftLine(line.key, { unit_price: event.target.value })} required /></label><label>تكلفة إضافية<input type="number" min="0" step="0.01" value={line.additional_unit_cost} onChange={(event) => updateDraftLine(line.key, { additional_unit_cost: event.target.value })} /></label></div>
              {draftLines.length > 1 ? <button type="button" className="mini-action purchase-line-delete" aria-label="حذف البند" onClick={() => setDraftLines((current) => current.filter((item) => item.key !== line.key))}><Trash2 size={15} /></button> : null}
            </div>)}</div>
            <fieldset className="advance-inline"><legend>الدفعة المقدمة</legend><label className="check-row"><input type="checkbox" checked={advanceEnabled} onChange={(event) => setAdvanceEnabled(event.target.checked)}/> سداد دفعة للمورد مع إنشاء الأمر</label>{advanceEnabled ? <><div className="form-pair"><label>المبلغ<input type="number" min="0.01" step="0.01" value={advanceAmount} onChange={(event) => setAdvanceAmount(event.target.value)} required/></label><label>الطريقة<select value={advanceMethod} onChange={(event) => setAdvanceMethod(event.target.value as PaymentMethod)}><option value="cash">نقدي</option><option value="bank_transfer">تحويل بنكي</option><option value="cheque">شيك</option><option value="wallet">محفظة</option></select></label></div><label>الحساب المالي<select value={advanceAccountId} onChange={(event) => setAdvanceAccountId(event.target.value)} required>{advanceAccounts.map((item) => <option key={item.id} value={item.id}>{item.name_ar}</option>)}</select></label></> : null}</fieldset>
            <label>ملاحظات<textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="شروط التوريد أو ملاحظات داخلية..." /></label>
            <button className="primary-button" disabled={submitting || (advanceEnabled && !advanceAccountId)}><FilePlus2 size={17} /> حفظ أمر الشراء كمسودة</button>
          </form> : <div className="setup-note"><PackageCheck size={20} /><div><strong>أكمل البيانات الأساسية أولًا</strong><p>يلزم وجود مورد وصنف ومخزن نشط قبل إنشاء أمر شراء.</p></div></div>}
        </article> : null}
      </section>

      {selected ? <section className="panel purchase-detail">
        <header className="panel__head"><div><h3>تفاصيل {selected.order_number}</h3><p>{selected.supplier_name_ar} · مخزن {selected.warehouse_name_ar} · {new Date(selected.order_date).toLocaleDateString("ar-EG")}</p></div><span className={`purchase-status ${statusMeta[selected.status].className}`}>{statusMeta[selected.status].label}</span></header>
        <div className="data-table-wrap"><table className="data-table purchase-lines-table"><thead><tr><th>الصنف</th><th>الأساس</th><th>المطلوب</th><th>المستلم الإجمالي</th><th>نسبة التنفيذ</th><th>السعر + الإضافي</th><th>الإجمالي</th></tr></thead><tbody>{selected.lines.map((line) => {
          const ordered = Number(line.cost_basis === "quantity" ? line.ordered_quantity : line.ordered_weight_kg);
          const received = Number(line.cost_basis === "quantity" ? line.received_quantity : line.received_weight_kg);
          const progress = ordered ? Math.min(100, (received / ordered) * 100) : 0;
          return <tr key={line.id}><td><strong>{line.product_name_ar}</strong><small dir="ltr">{line.product_code}</small></td><td>{line.cost_basis === "quantity" ? "كمية" : "وزن"}</td><td className="numeric-cell">{number.format(ordered)}</td><td className="numeric-cell">{number.format(received)}</td><td><div className="purchase-progress"><span style={{ width: `${progress}%` }} /><small>{number.format(progress)}%</small></div></td><td className="numeric-cell">{currency.format(Number(line.unit_price) + Number(line.additional_unit_cost))}</td><td className="numeric-cell"><strong>{currency.format(Number(line.line_total))}</strong></td></tr>;
        })}</tbody></table></div>

        {canManage ? <div className="purchase-actions-zone">
          {selected.status === "draft" ? <div className="purchase-action-callout"><span><BadgeCheck size={22} /></span><div><strong>الأمر جاهز للمراجعة</strong><p>الاعتماد يقفل بيانات الأمر ويسمح بتسجيل الاستلامات.</p></div><button className="primary-button" onClick={() => void approveSelected()} disabled={submitting}><BadgeCheck size={17} /> اعتماد الأمر</button></div> : null}
          {["approved", "partially_received"].includes(selected.status) ? <form className="purchase-receipt-form" onSubmit={submitReceipt}>
            <header><span><Truck size={21} /></span><div><strong>تسجيل سند استلام</strong><p>أدخل الإجمالي والفاقد؛ النظام يضيف الصافي فقط للمخزون ويعيد توزيع التكلفة.</p></div></header>
            <div className="purchase-receipt-lines">{selected.lines.map((line) => {
              const draft = receiptValue(line);
              return <div className="purchase-receipt-line" key={line.id}><strong>{line.product_name_ar}</strong><label>إجمالي الكمية<input type="number" min="0" step="0.001" value={draft.gross_quantity} onChange={(event) => updateReceipt(line.id, { gross_quantity: event.target.value })} /></label><label>إجمالي الوزن<input type="number" min="0" step="0.001" value={draft.gross_weight_kg} onChange={(event) => updateReceipt(line.id, { gross_weight_kg: event.target.value })} /></label><label>فاقد الكمية<input type="number" min="0" step="0.001" value={draft.loss_quantity} onChange={(event) => updateReceipt(line.id, { loss_quantity: event.target.value })} /></label><label>فاقد الوزن<input type="number" min="0" step="0.001" value={draft.loss_weight_kg} onChange={(event) => updateReceipt(line.id, { loss_weight_kg: event.target.value })} /></label><label>رقم التشغيلة<input value={draft.lot_number} onChange={(event) => updateReceipt(line.id, { lot_number: event.target.value })} /></label></div>;
            })}</div>
            <div className="purchase-receipt-foot"><label>ملاحظات الاستلام<input value={receiptNotes} onChange={(event) => setReceiptNotes(event.target.value)} /></label><button className="primary-button" disabled={submitting}><ClipboardCheck size={17} /> ترحيل الاستلام</button></div>
          </form> : null}
          {["approved", "partially_received", "received"].includes(selected.status) ? <form className="purchase-invoice-form" onSubmit={createInvoice}><span><ReceiptText size={20} /></span><div><strong>فاتورة المورد</strong><small>اربط رقم فاتورة المورد بقيمة الأمر المعتمدة</small></div><input value={supplierInvoiceNumber} onChange={(event) => setSupplierInvoiceNumber(event.target.value)} placeholder="رقم فاتورة المورد" required /><button className="secondary-button" disabled={submitting}><ReceiptText size={16} /> تسجيل الفاتورة</button></form> : null}
        </div> : null}
        {receipts.length ? <div className="purchase-receipt-history">
          <header><div><strong>سندات الاستلام</strong><small>سجل غير قابل للتعديل لكل دفعة تم ترحيلها</small></div><span>{receipts.length} سند</span></header>
          {receipts.map((receipt) => <div className={`purchase-receipt-history__row ${receipt.status === "reversed" ? "purchase-receipt-history__row--reversed" : ""}`} key={receipt.id}>
            <span className="purchase-order-card__icon"><ReceiptText size={17} /></span>
            <span><strong dir="ltr">{receipt.receipt_number}</strong><small>{new Date(receipt.posted_at).toLocaleString("ar-EG")} · {receipt.lines.length} بند</small></span>
            <span className={`purchase-status ${receipt.status === "posted" ? "purchase-status--received" : "purchase-status--cancelled"}`}>{receipt.status === "posted" ? "مرحّل" : "معكوس"}</span>
            <strong className="numeric-cell">{currency.format(receipt.lines.reduce((sum, line) => sum + Number(line.capitalized_cost), 0))} ج.م</strong>
            {canManage && receipt.status === "posted" ? <button type="button" className="mini-action purchase-reversal-trigger" aria-label="عكس سند الاستلام" onClick={() => { setReversalTargetId(receipt.id); setReversalReason(""); }}><Undo2 size={15} /></button> : null}
            {receipt.status === "reversed" ? <small className="purchase-reversal-reason">سبب العكس: {receipt.reversal_reason}</small> : null}
          </div>)}
          {reversalTargetId ? <form className="purchase-reversal-bar" onSubmit={reverseReceipt}><Undo2 size={18} /><span><strong>عكس سند الاستلام</strong><small>لن يتم العكس إذا صُرف أي جزء من طبقة FIFO أو وُجدت فاتورة مورد مرحّلة.</small></span><input value={reversalReason} onChange={(event) => setReversalReason(event.target.value)} minLength={3} placeholder="سبب العكس بالتفصيل" required /><button className="danger-button secondary-button" disabled={submitting}><Undo2 size={15} /> تأكيد العكس</button><button type="button" className="secondary-button" onClick={() => setReversalTargetId("")}>إلغاء</button></form> : null}
        </div> : null}
        <footer className="purchase-detail-total"><span><Scale size={18} /> التكلفة تشمل السعر والمصاريف الإضافية</span><strong>{currency.format(Number(selected.total))} ج.م</strong></footer>
      </section> : null}
    </AppShell>
  );
}
