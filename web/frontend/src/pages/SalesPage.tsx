import {
  BadgeDollarSign,
  Check,
  FileText,
  PackageCheck,
  Plus,
  RefreshCw,
  Scale,
  ShoppingCart,
  Trash2,
  Truck,
  Undo2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { clientId } from "../lib/clientId";

type SalesTab = "piece" | "weight" | "quotation";
type PaymentMethod = "cash" | "bank_transfer" | "cheque" | "wallet";
type Option = { id: string; code: string; name_ar: string; standard_weight_kg: string; unit_symbol: string; account_type: string };
type Options = { customers: Option[]; warehouses: Option[]; products: Option[]; financial_accounts: Option[] };
type Status = "draft" | "delivered" | "reversed" | "cancelled";
type OrderLine = {
  id: string; product_id: string; product_code: string; product_name_ar: string;
  quantity: string; unit: string; unit_price: string; line_total: string; standard_weight_kg: string;
  billing_weight_kg: string; price_per_kg: string; notes: string;
};
type Delivery = {
  id: string; delivery_number: string; status: "posted" | "reversed";
  lines: Array<{ id: string; product_name_ar: string; quantity: string; weight_kg: string; cost_amount: string }>;
};
type Invoice = { invoice_number: string; invoice_type: "standard" | "weight"; status: "posted" | "reversed"; total: string };
type WeightCard = {
  card_number: string; net_weight_kg: string; vehicle_number: string; weight_mode: string;
  pricing_mode: string; status: string;
};
type SalesOrder = {
  id: string; order_number: string; customer_name_ar: string; warehouse_name_ar: string;
  billing_method: "piece" | "weight"; status: Status; order_date: string; notes: string;
  subtotal: string; discount_amount: string; transport_amount: string; tax_amount: string;
  total: string; version: number; lines: OrderLine[]; weight_cards: WeightCard[];
  invoice: Invoice | null; delivery: Delivery | null;
};
type Quotation = {
  id: string; quotation_number: string; customer_name_ar: string; quotation_date: string;
  valid_until: string | null; status: string; total: string;
  lines: Array<{ id: string; item_name: string; quantity: string; unit: string; unit_price: string; line_total: string }>;
};
type PieceDraft = { key: string; product_id: string; quantity: string; unit: string; unit_price: string; notes: string };
type WeightDraft = PieceDraft & { actual_weight_kg: string; price_per_kg: string };
type QuoteDraft = { key: string; product_id: string; item_name: string; quantity: string; unit: string; unit_price: string };

const currency = new Intl.NumberFormat("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const quantityFormat = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 3 });
const statusLabels: Record<Status, string> = { draft: "مسودة", delivered: "تم التسليم", reversed: "معكوس", cancelled: "ملغي" };
const key = () => clientId();
const pieceLine = (productId = "", unit = ""): PieceDraft => ({ key: key(), product_id: productId, quantity: "", unit, unit_price: "", notes: "" });
const weightLine = (productId = ""): WeightDraft => ({ ...pieceLine(productId), actual_weight_kg: "", price_per_kg: "" });
const quoteLine = (productId = ""): QuoteDraft => ({ key: key(), product_id: productId, item_name: "", quantity: "", unit: "ماسورة", unit_price: "" });

export function SalesPage() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const canPiece = user?.permissions.includes("sales.read") ?? false;
  const canPieceManage = user?.permissions.includes("sales.manage") ?? false;
  const canWeight = user?.permissions.includes("weight_sales.read") ?? false;
  const canWeightManage = user?.permissions.includes("weight_sales.manage") ?? false;
  const initialTab: SalesTab = location.pathname.includes("weight") ? "weight" : "piece";
  const createRequested = new URLSearchParams(location.search).get("focus") === "new";
  const [tab, setTab] = useState<SalesTab>(initialTab);
  const [showCreate, setShowCreate] = useState(createRequested);
  const [options, setOptions] = useState<Options>({ customers: [], warehouses: [], products: [], financial_accounts: [] });
  const [orders, setOrders] = useState<SalesOrder[]>([]);
  const [quotations, setQuotations] = useState<Quotation[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [notes, setNotes] = useState("");
  const [pieceLines, setPieceLines] = useState<PieceDraft[]>([pieceLine()]);
  const [weightLines, setWeightLines] = useState<WeightDraft[]>([weightLine()]);
  const [weightMode, setWeightMode] = useState<"total_card" | "per_line">("total_card");
  const [pricingMode, setPricingMode] = useState<"uniform" | "per_line">("uniform");
  const [netWeight, setNetWeight] = useState("");
  const [uniformPrice, setUniformPrice] = useState("");
  const [vehicleScale, setVehicleScale] = useState(false);
  const [grossWeight, setGrossWeight] = useState("");
  const [tareWeight, setTareWeight] = useState("");
  const [vehicleNumber, setVehicleNumber] = useState("");
  const [discount, setDiscount] = useState("");
  const [transport, setTransport] = useState("");
  const [tax, setTax] = useState("");
  const [advanceEnabled, setAdvanceEnabled] = useState(false);
  const [advanceAmount, setAdvanceAmount] = useState("");
  const [advanceMethod, setAdvanceMethod] = useState<PaymentMethod>("cash");
  const [advanceAccountId, setAdvanceAccountId] = useState("");
  const [quoteLines, setQuoteLines] = useState<QuoteDraft[]>([quoteLine()]);
  const [validUntil, setValidUntil] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [reversalReason, setReversalReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const createRef = useRef<HTMLElement>(null);
  const detailRef = useRef<HTMLElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const requests: [Promise<SalesOrder[]>, Promise<Options>, Promise<Quotation[]> | null] = [
        api<SalesOrder[]>("/sales/orders?limit=150"), api<Options>("/sales/options"),
        canPiece ? api<Quotation[]>("/sales/quotations?limit=100") : null,
      ];
      const [orderRows, optionRows, quoteRows] = await Promise.all([
        requests[0], requests[1], requests[2] ?? Promise.resolve([]),
      ]);
      setOrders(orderRows); setOptions(optionRows); setQuotations(quoteRows);
      setSelectedId((current) => current || orderRows[0]?.id || "");
      setCustomerId((current) => current || optionRows.customers[0]?.id || "");
      setWarehouseId((current) => current || optionRows.warehouses[0]?.id || "");
      setAdvanceAccountId((current) => current || optionRows.financial_accounts.find((item) => item.account_type === "cash")?.id || "");
      const firstProduct = optionRows.products[0]?.id || "";
      const defaultUnit = optionRows.products[0]?.unit_symbol || "قطعة";
      setPieceLines((current) => current.map((line) => ({ ...line, product_id: line.product_id || firstProduct, unit: line.unit || defaultUnit })));
      setWeightLines((current) => current.map((line) => ({ ...line, product_id: line.product_id || firstProduct, unit: line.unit || defaultUnit })));
      setQuoteLines((current) => current.map((line) => ({ ...line, product_id: line.product_id || firstProduct })));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل مساحة المبيعات");
    } finally { setLoading(false); }
  }, [canPiece]);

  const advanceAccountType = { cash: "cash", bank_transfer: "bank", cheque: "bank", wallet: "wallet" }[advanceMethod];
  const advanceAccounts = useMemo(() => options.financial_accounts.filter((item) => item.account_type === advanceAccountType), [advanceAccountType, options.financial_accounts]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!createRequested) return;
    setShowCreate(true);
    window.requestAnimationFrame(() => createRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [createRequested]);
  useEffect(() => {
    if (!advanceAccounts.some((item) => item.id === advanceAccountId)) {
      setAdvanceAccountId(advanceAccounts[0]?.id || "");
    }
  }, [advanceAccountId, advanceAccounts]);
  const selected = orders.find((order) => order.id === selectedId) ?? null;
  const visibleOrders = useMemo(
    () => orders.filter((order) => order.billing_method === (tab === "weight" ? "weight" : "piece")),
    [orders, tab],
  );
  useEffect(() => {
    if (tab === "quotation" || visibleOrders.some((order) => order.id === selectedId)) return;
    setSelectedId(visibleOrders[0]?.id || "");
  }, [selectedId, tab, visibleOrders]);
  const stats = useMemo(() => ({
    drafts: orders.filter((x) => x.status === "draft").length,
    delivered: orders.filter((x) => x.status === "delivered").length,
    weight: orders.filter((x) => x.billing_method === "weight").length,
    value: orders.filter((x) => x.status === "delivered").reduce((sum, x) => sum + Number(x.total), 0),
  }), [orders]);

  function switchTab(value: SalesTab) {
    setTab(value); setError(""); setNotice("");
    setShowCreate(false);
    if (value === "weight") navigate("/weight-sales", { replace: true });
    else navigate("/sales", { replace: true });
  }
  function selectOrder(orderId: string) {
    setSelectedId(orderId);
    setShowCreate(false);
    window.requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }
  function productName(productId: string) { return options.products.find((x) => x.id === productId)?.name_ar ?? ""; }
  function productUnit(productId: string) { return options.products.find((x) => x.id === productId)?.unit_symbol || "قطعة"; }
  function updatePiece(lineKey: string, patch: Partial<PieceDraft>) { setPieceLines((rows) => rows.map((x) => x.key === lineKey ? { ...x, ...patch } : x)); }
  function updateWeight(lineKey: string, patch: Partial<WeightDraft>) { setWeightLines((rows) => rows.map((x) => x.key === lineKey ? { ...x, ...patch } : x)); }
  function updateQuote(lineKey: string, patch: Partial<QuoteDraft>) { setQuoteLines((rows) => rows.map((x) => x.key === lineKey ? { ...x, ...patch } : x)); }

  async function submitPiece(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError(""); setNotice("");
    try {
      const created = await api<SalesOrder>("/sales/orders", { method: "POST", body: JSON.stringify({ customer_id: customerId, warehouse_id: warehouseId, notes, advance_amount: advanceEnabled ? advanceAmount : "0", advance_payment_method: advanceMethod, advance_financial_account_id: advanceEnabled ? advanceAccountId : null, lines: pieceLines.map(({ product_id, quantity, unit, unit_price, notes: lineNotes }) => ({ product_id, quantity, unit, unit_price, notes: lineNotes })) }) });
      setPieceLines([pieceLine(options.products[0]?.id, options.products[0]?.unit_symbol)]); setNotes(""); setSelectedId(created.id);
      setShowCreate(false);
      setAdvanceEnabled(false); setAdvanceAmount("");
      setNotice(`تم إنشاء أمر البيع ${created.order_number} كمسودة.`); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء أمر البيع"); }
    finally { setSubmitting(false); }
  }

  async function submitWeight(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError(""); setNotice("");
    try {
      const created = await api<SalesOrder>("/sales/weight-orders", { method: "POST", body: JSON.stringify({
        customer_id: customerId, warehouse_id: warehouseId, weight_mode: weightMode, pricing_mode: pricingMode,
        total_actual_weight_kg: netWeight || null, uniform_price_per_kg: uniformPrice || null,
        use_vehicle_scale: vehicleScale, gross_weight_kg: grossWeight || "0", tare_weight_kg: tareWeight || "0",
        vehicle_number: vehicleNumber, discount_amount: discount || "0", transport_amount: transport || "0",
        tax_amount: tax || "0", notes, advance_amount: advanceEnabled ? advanceAmount : "0", advance_payment_method: advanceMethod, advance_financial_account_id: advanceEnabled ? advanceAccountId : null, lines: weightLines.map(({ product_id, quantity, unit, actual_weight_kg, price_per_kg, notes: lineNotes }) => ({ product_id, quantity, unit, actual_weight_kg: actual_weight_kg || null, price_per_kg: price_per_kg || null, notes: lineNotes })),
      }) });
      setSelectedId(created.id); setNotice(`تم حفظ كارتة ${created.weight_cards[0]?.card_number} كمسودة للمراجعة.`);
      setShowCreate(false);
      setWeightLines([{ ...weightLine(options.products[0]?.id), unit: options.products[0]?.unit_symbol || "ماسورة" }]); setNetWeight(""); setNotes(""); await load();
      setAdvanceEnabled(false); setAdvanceAmount("");
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء بيع الوزن"); }
    finally { setSubmitting(false); }
  }

  async function submitQuotation(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError(""); setNotice("");
    try {
      const created = await api<Quotation>("/sales/quotations", { method: "POST", body: JSON.stringify({ customer_id: customerId, valid_until: validUntil ? new Date(`${validUntil}T12:00:00`).toISOString() : null, notes, lines: quoteLines.map((line) => ({ product_id: line.product_id || null, item_name: line.item_name || productName(line.product_id), quantity: line.quantity, unit: line.unit, unit_price: line.unit_price })) }) });
      setNotice(`تم إنشاء عرض السعر ${created.quotation_number} دون أي تأثير على المخزون أو الحسابات.`);
      setQuoteLines([quoteLine(options.products[0]?.id)]); setValidUntil(""); setNotes(""); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء عرض السعر"); }
    finally { setSubmitting(false); }
  }

  async function deliver() {
    if (!selected) return; setSubmitting(true); setError("");
    try {
      const result = await api<SalesOrder>(`/sales/orders/${selected.id}/delivery`, { method: "POST", headers: { "Idempotency-Key": clientId("sales") }, body: JSON.stringify({ version: selected.version }) });
      setNotice(`تم التسليم وإنشاء فاتورة العميل ${result.invoice?.invoice_number}.`); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "تعذر تسليم أمر البيع"); }
    finally { setSubmitting(false); }
  }

  async function reverseDelivery(event: FormEvent) {
    event.preventDefault(); if (!selected?.delivery) return; setSubmitting(true); setError("");
    try {
      await api(`/sales/deliveries/${selected.delivery.id}/reversal`, { method: "POST", headers: { "Idempotency-Key": clientId("sales-reversal") }, body: JSON.stringify({ reason: reversalReason }) });
      setReversalReason(""); setNotice("تم عكس التسليم والفاتورة وإعادة العدد والوزن والتكلفة إلى FIFO."); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "تعذر عكس التسليم"); }
    finally { setSubmitting(false); }
  }

  async function cancelDraft(event: FormEvent) {
    event.preventDefault(); if (!selected) return; setSubmitting(true); setError("");
    try {
      await api(`/sales/orders/${selected.id}/cancellation`, { method: "POST", body: JSON.stringify({ version: selected.version, reason: cancelReason }) });
      setCancelReason(""); setNotice("تم إلغاء المسودة مع الاحتفاظ بأثر المراجعة."); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "تعذر إلغاء المسودة"); }
    finally { setSubmitting(false); }
  }

  const canManageCurrent = tab === "weight" ? canWeightManage : canPieceManage;
  const setupReady = options.customers.length > 0 && options.warehouses.length > 0 && options.products.length > 0;
  return <AppShell>
    <section className="page-heading sales-heading"><div><span className="eyebrow">المرحلة السادسة · المبيعات</span><h2>المبيعات والفوترة</h2><p>بيع بالقطعة أو بالوزن الفعلي، مع FIFO وفاتورة عميل وسجل عكس قابل للمراجعة.</p></div><div className="page-heading__actions">{canManageCurrent && tab !== "quotation" ? <button className="secondary-button" onClick={() => { setShowCreate(true); window.requestAnimationFrame(() => createRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })); }}><Plus size={17}/> {tab === "weight" ? "كارتة وزن جديدة" : "أمر بيع جديد"}</button> : null}<button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17}/> تحديث</button></div></section>
    {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
    {notice ? <div className="alert alert--success"><Check size={17}/>{notice}</div> : null}
    <section className="inventory-stats"><article><span className="inventory-stat__icon"><FileText size={20}/></span><span><small>مسودات</small><strong>{stats.drafts}</strong></span></article><article><span className="inventory-stat__icon inventory-stat__icon--blue"><Truck size={20}/></span><span><small>تم تسليمها</small><strong>{stats.delivered}</strong></span></article><article><span className="inventory-stat__icon inventory-stat__icon--amber"><Scale size={20}/></span><span><small>كروت وزن</small><strong>{stats.weight}</strong></span></article><article><span className="inventory-stat__icon inventory-stat__icon--violet"><BadgeDollarSign size={20}/></span><span><small>قيمة الفواتير</small><strong>{currency.format(stats.value)} <em>ج.م</em></strong></span></article></section>
    <div className="sales-tabs" role="tablist">
      {canPiece ? <button className={tab === "piece" ? "active" : ""} onClick={() => switchTab("piece")}><ShoppingCart size={17}/> بيع بالقطعة</button> : null}
      {canWeight ? <button className={tab === "weight" ? "active" : ""} onClick={() => switchTab("weight")}><Scale size={17}/> بيع بالوزن</button> : null}
      {canPiece ? <button className={tab === "quotation" ? "active" : ""} onClick={() => switchTab("quotation")}><FileText size={17}/> عروض الأسعار</button> : null}
    </div>
    {tab !== "quotation" ? <section className={`master-layout sales-layout ${canManageCurrent ? "" : "master-layout--single"}`}>
      <article className="panel"><header className="panel__head"><div><h3>{tab === "weight" ? "فواتير الوزن" : "أوامر البيع"}</h3><p>اختر المستند للمراجعة أو التسليم</p></div><span className="status-badge status-badge--active">{visibleOrders.length}</span></header><div className="purchase-order-list">{visibleOrders.map((order) => <button className={`purchase-order-card ${selectedId === order.id ? "purchase-order-card--selected" : ""}`} key={order.id} onClick={() => selectOrder(order.id)}><span className="purchase-order-card__icon">{order.billing_method === "weight" ? <Scale size={18}/> : <ShoppingCart size={18}/>}</span><span><strong dir="ltr">{order.order_number}</strong><small>{order.customer_name_ar} · {order.lines.length} بند</small></span><span className={`purchase-status purchase-status--${order.status === "delivered" ? "received" : order.status === "draft" ? "draft" : "cancelled"}`}>{statusLabels[order.status]}</span><span className="purchase-order-card__value">{currency.format(Number(order.total))} ج.م</span></button>)}</div></article>
      {canManageCurrent && showCreate && !setupReady ? <article ref={createRef} className="panel master-form-card sales-create-card"><header className="panel__head"><div><h3>{tab === "weight" ? "كارتة وزن جديدة" : "أمر بيع جديد"}</h3><p>المستند يبقى مسودة حتى الاعتماد والتسليم</p></div><button type="button" className="mini-action" aria-label="إغلاق نموذج الإنشاء" onClick={() => setShowCreate(false)}><X size={17}/></button></header><div className="setup-note"><PackageCheck size={20}/><div><strong>أكمل البيانات الأساسية أولًا</strong><p>يلزم وجود عميل وصنف ومخزن نشط قبل إنشاء أمر بيع.</p></div></div></article> : null}
      {canManageCurrent && setupReady && showCreate ? <article ref={createRef} className="panel master-form-card sales-create-card"><header className="panel__head"><div><h3>{tab === "weight" ? "كارتة وزن جديدة" : "أمر بيع جديد"}</h3><p>المستند يبقى مسودة حتى الاعتماد والتسليم</p></div><button type="button" className="mini-action" aria-label="إغلاق نموذج الإنشاء" onClick={() => setShowCreate(false)}><X size={17}/></button></header>
        <form className="compact-form sales-form" onSubmit={tab === "weight" ? submitWeight : submitPiece}><div className="form-pair"><label>العميل<select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>{options.customers.map((x) => <option key={x.id} value={x.id}>{x.name_ar} · {x.code}</option>)}</select></label><label>المخزن<select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>{options.warehouses.map((x) => <option key={x.id} value={x.id}>{x.name_ar}</option>)}</select></label></div>
          {tab === "weight" ? <><div className="form-pair"><label>طريقة الوزن<select value={weightMode} onChange={(e) => setWeightMode(e.target.value as typeof weightMode)}><option value="total_card">وزن إجمالي للكارتة</option><option value="per_line">وزن لكل بند</option></select></label><label>طريقة التسعير<select value={pricingMode} onChange={(e) => setPricingMode(e.target.value as typeof pricingMode)}><option value="uniform">سعر كيلو موحد</option><option value="per_line">سعر لكل بند</option></select></label></div><label className="check-row"><input type="checkbox" checked={vehicleScale} onChange={(e) => setVehicleScale(e.target.checked)}/> حساب الصافي من ميزان السيارة</label>{vehicleScale ? <div className="form-pair"><label>الوزن القائم<input type="number" min="0" step="0.001" value={grossWeight} onChange={(e) => setGrossWeight(e.target.value)} required/></label><label>وزن السيارة الفارغ<input type="number" min="0" step="0.001" value={tareWeight} onChange={(e) => setTareWeight(e.target.value)} required/></label></div> : weightMode === "total_card" ? <label>الوزن الصافي الفعلي<input type="number" min="0.001" step="0.001" value={netWeight} onChange={(e) => setNetWeight(e.target.value)} required/></label> : null}{pricingMode === "uniform" ? <label>سعر الكيلو الموحد<input type="number" min="0" step="0.01" value={uniformPrice} onChange={(e) => setUniformPrice(e.target.value)} required/></label> : null}<label>رقم السيارة<input value={vehicleNumber} onChange={(e) => setVehicleNumber(e.target.value)}/></label></> : null}
          <div className="purchase-lines-head"><strong>البنود</strong><button type="button" className="text-button" onClick={() => tab === "weight" ? setWeightLines((x) => [...x, { ...weightLine(options.products[0]?.id), unit: options.products[0]?.unit_symbol || "ماسورة" }]) : setPieceLines((x) => [...x, pieceLine(options.products[0]?.id, options.products[0]?.unit_symbol || "قطعة")])}><Plus size={15}/> إضافة بند</button></div>
          <div className="sales-draft-lines">{(tab === "weight" ? weightLines : pieceLines).map((line, index) => <div className="sales-draft-line" key={line.key}><span className="purchase-line-number">{index + 1}</span><label>الصنف<select value={line.product_id} onChange={(e) => tab === "weight" ? updateWeight(line.key, { product_id: e.target.value, unit: productUnit(e.target.value) }) : updatePiece(line.key, { product_id: e.target.value, unit: productUnit(e.target.value) })}>{options.products.map((x) => <option key={x.id} value={x.id}>{x.name_ar} · {x.code}</option>)}</select></label><label>العدد<input type="number" min="0.001" step="0.001" value={line.quantity} onChange={(e) => tab === "weight" ? updateWeight(line.key, { quantity: e.target.value }) : updatePiece(line.key, { quantity: e.target.value })} required/></label><label>الوحدة<input value={line.unit} maxLength={40} onChange={(e) => tab === "weight" ? updateWeight(line.key, { unit: e.target.value }) : updatePiece(line.key, { unit: e.target.value })} required/></label>{tab === "piece" ? <label>سعر الوحدة<input type="number" min="0" step="0.01" value={line.unit_price} onChange={(e) => updatePiece(line.key, { unit_price: e.target.value })} required/></label> : <>{weightMode === "per_line" ? <label>الوزن الفعلي<input type="number" min="0.001" step="0.001" value={(line as WeightDraft).actual_weight_kg} onChange={(e) => updateWeight(line.key, { actual_weight_kg: e.target.value })} required/></label> : null}{pricingMode === "per_line" ? <label>سعر الكيلو<input type="number" min="0" step="0.01" value={(line as WeightDraft).price_per_kg} onChange={(e) => updateWeight(line.key, { price_per_kg: e.target.value })} required/></label> : null}</>}<button type="button" className="mini-action" aria-label="حذف" onClick={() => tab === "weight" ? setWeightLines((x) => x.length > 1 ? x.filter((y) => y.key !== line.key) : x) : setPieceLines((x) => x.length > 1 ? x.filter((y) => y.key !== line.key) : x)}><Trash2 size={14}/></button></div>)}</div>
          {tab === "weight" ? <div className="sales-adjustments"><label>خصم<input type="number" min="0" step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)}/></label><label>نقل<input type="number" min="0" step="0.01" value={transport} onChange={(e) => setTransport(e.target.value)}/></label><label>ضريبة<input type="number" min="0" step="0.01" value={tax} onChange={(e) => setTax(e.target.value)}/></label></div> : null}
          <fieldset className="advance-inline"><legend>الدفعة المقدمة</legend><label className="check-row"><input type="checkbox" checked={advanceEnabled} onChange={(e) => setAdvanceEnabled(e.target.checked)}/> تحصيل دفعة مع إنشاء الأمر</label>{advanceEnabled ? <><div className="form-pair"><label>المبلغ<input type="number" min="0.01" step="0.01" value={advanceAmount} onChange={(e) => setAdvanceAmount(e.target.value)} required/></label><label>الطريقة<select value={advanceMethod} onChange={(e) => setAdvanceMethod(e.target.value as PaymentMethod)}><option value="cash">نقدي</option><option value="bank_transfer">تحويل بنكي</option><option value="cheque">شيك</option><option value="wallet">محفظة</option></select></label></div><label>الحساب المالي<select value={advanceAccountId} onChange={(e) => setAdvanceAccountId(e.target.value)} required>{advanceAccounts.map((item) => <option key={item.id} value={item.id}>{item.name_ar}</option>)}</select></label></> : null}</fieldset>
          <label>ملاحظات<textarea value={notes} onChange={(e) => setNotes(e.target.value)}/></label><button className="primary-button" disabled={submitting || (advanceEnabled && !advanceAccountId)}>{tab === "weight" ? <Scale size={17}/> : <ShoppingCart size={17}/>} حفظ كمسودة</button></form></article> : null}
    </section> : <section className="master-layout sales-layout"><article className="panel"><header className="panel__head"><div><h3>عروض الأسعار</h3><p>مستند تجاري بلا تأثير على المخزون أو حساب العميل</p></div><span className="status-badge status-badge--active">{quotations.length}</span></header><div className="quotation-list">{quotations.map((q) => <div className="quotation-card" key={q.id}><span><strong dir="ltr">{q.quotation_number}</strong><small>{q.customer_name_ar} · {new Date(q.quotation_date).toLocaleDateString("ar-EG")}</small></span><span>{q.lines.length} بند</span><strong>{currency.format(Number(q.total))} ج.م</strong></div>)}</div></article>{canPieceManage && setupReady ? <article className="panel master-form-card"><header className="panel__head"><div><h3>عرض سعر جديد</h3><p>يسمح ببنود حرة غير مسجلة كمنتج</p></div><FileText size={20}/></header><form className="compact-form sales-form" onSubmit={submitQuotation}><label>العميل<select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>{options.customers.map((x) => <option key={x.id} value={x.id}>{x.name_ar}</option>)}</select></label><label>صالح حتى<input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)}/></label><div className="purchase-lines-head"><strong>البنود</strong><button type="button" className="text-button" onClick={() => setQuoteLines((x) => [...x, quoteLine(options.products[0]?.id)])}><Plus size={15}/> إضافة</button></div>{quoteLines.map((line) => <div className="quote-draft-line" key={line.key}><label>منتج اختياري<select value={line.product_id} onChange={(e) => updateQuote(line.key, { product_id: e.target.value, item_name: productName(e.target.value) })}><option value="">بند حر</option>{options.products.map((x) => <option key={x.id} value={x.id}>{x.name_ar}</option>)}</select></label><label>اسم البند<input value={line.item_name || productName(line.product_id)} onChange={(e) => updateQuote(line.key, { item_name: e.target.value })} required/></label><div className="form-pair"><label>الكمية<input type="number" min="0.001" step="0.001" value={line.quantity} onChange={(e) => updateQuote(line.key, { quantity: e.target.value })} required/></label><label>السعر<input type="number" min="0" step="0.01" value={line.unit_price} onChange={(e) => updateQuote(line.key, { unit_price: e.target.value })} required/></label></div></div>)}<label>ملاحظات<textarea value={notes} onChange={(e) => setNotes(e.target.value)}/></label><button className="primary-button" disabled={submitting}><FileText size={17}/> حفظ عرض السعر</button></form></article> : null}</section>}
    {selected && tab !== "quotation" && selected.billing_method === tab ? <section ref={detailRef} className="panel sales-detail"><header className="panel__head"><div><h3>تفاصيل {selected.order_number}</h3><p>{selected.customer_name_ar} · {selected.warehouse_name_ar} · {new Date(selected.order_date).toLocaleString("ar-EG")}</p></div><span className={`purchase-status purchase-status--${selected.status === "delivered" ? "received" : selected.status === "draft" ? "draft" : "cancelled"}`}>{statusLabels[selected.status]}</span></header>{selected.weight_cards[0] ? <div className="weight-card-summary"><span><Scale size={18}/><strong>{selected.weight_cards[0].card_number}</strong></span><span>الوزن: <strong>{quantityFormat.format(Number(selected.weight_cards[0].net_weight_kg))} كجم</strong></span><span>السيارة: <strong>{selected.weight_cards[0].vehicle_number || "—"}</strong></span></div> : null}<div className="data-table-wrap"><table className="data-table"><thead><tr><th>الصنف</th><th>العدد</th><th>الوحدة</th>{selected.billing_method === "weight" ? <><th>الوزن الفعلي</th><th>سعر الكيلو</th></> : <th>سعر الوحدة</th>}<th>الإجمالي</th></tr></thead><tbody>{selected.lines.map((line) => <tr key={line.id}><td><strong>{line.product_name_ar}</strong><small dir="ltr">{line.product_code}</small></td><td>{quantityFormat.format(Number(line.quantity))}</td><td>{line.unit}</td>{selected.billing_method === "weight" ? <><td>{quantityFormat.format(Number(line.billing_weight_kg))} كجم</td><td>{currency.format(Number(line.price_per_kg))}</td></> : <td>{currency.format(Number(line.unit_price))}</td>}<td><strong>{currency.format(Number(line.line_total))}</strong></td></tr>)}</tbody></table></div><div className="sales-total-strip"><span>الإجمالي الفرعي {currency.format(Number(selected.subtotal))}</span>{selected.billing_method === "weight" ? <span>خصم {currency.format(Number(selected.discount_amount))} · نقل {currency.format(Number(selected.transport_amount))} · ضريبة {currency.format(Number(selected.tax_amount))}</span> : null}<strong>{currency.format(Number(selected.total))} ج.م</strong></div>{selected.status === "draft" && canManageCurrent ? <><div className="sales-delivery-action"><div><PackageCheck size={22}/><span><strong>جاهز للتسليم</strong><small>سيُصرف المخزون وتُنشأ فاتورة العميل داخل معاملة واحدة.</small></span></div><button className="primary-button" onClick={() => void deliver()} disabled={submitting}><Truck size={17}/> اعتماد وتسليم</button></div><form className="sales-reversal sales-cancellation" onSubmit={cancelDraft}><Trash2 size={18}/><input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} minLength={3} placeholder="سبب إلغاء المسودة" required/><button className="secondary-button danger-button" disabled={submitting}>إلغاء المسودة</button></form></> : null}{selected.invoice ? <div className="invoice-chip"><BadgeDollarSign size={18}/><span><strong>{selected.invoice.invoice_number}</strong><small>{selected.invoice.invoice_type === "weight" ? "فاتورة وزن" : "فاتورة عادية"} · {selected.invoice.status === "posted" ? "مرحّلة" : "معكوسة"}</small></span><strong>{currency.format(Number(selected.invoice.total))} ج.م</strong></div> : null}{selected.delivery?.status === "posted" && canManageCurrent ? <form className="sales-reversal" onSubmit={reverseDelivery}><Undo2 size={18}/><input value={reversalReason} onChange={(e) => setReversalReason(e.target.value)} minLength={3} placeholder="سبب عكس التسليم" required/><button className="secondary-button danger-button" disabled={submitting}>عكس التسليم والفاتورة</button></form> : null}</section> : null}
  </AppShell>;
}
