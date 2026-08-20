import { BadgeDollarSign, Check, PackageOpen, ReceiptText, RefreshCw, RotateCcw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type ReturnType = "sales" | "purchase";
type RefundType = "customer_refund" | "supplier_refund";
type PaymentMethod = "cash" | "bank_transfer" | "cheque" | "wallet";
type Invoice = { id: string; invoice_number: string; partner_name_ar: string; original_total: string; returned_total: string; net_total: string; refundable: string };
type ReturnLine = { source_line_id: string; product_code: string; product_name_ar: string; unit: string; cost_basis: "quantity" | "weight"; remaining_quantity: string; remaining_weight_kg: string };
type ReturnDocument = { id: string; return_number: string; return_type: ReturnType; invoice_number: string; partner_name_ar: string; warehouse_name_ar: string; return_date: string; total: string; status: "posted" | "reversed"; version: number; lines: Array<{ product_name_ar: string; quantity: string; weight_kg: string }> };
type Refund = { id: string; refund_number: string; refund_type: RefundType; invoice_number: string; partner_name_ar: string; financial_account_name_ar: string; refund_date: string; amount: string; payment_method: PaymentMethod; status: "posted" | "reversed"; version: number };
type Account = { id: string; code: string; name_ar: string; type: string };

const currency = new Intl.NumberFormat("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const accountType: Record<PaymentMethod, string> = { cash: "cash", bank_transfer: "bank", cheque: "bank", wallet: "wallet" };
const methodLabel: Record<PaymentMethod, string> = { cash: "نقدي", bank_transfer: "تحويل بنكي", cheque: "شيك", wallet: "محفظة" };

export function ReturnsPage() {
  const { user } = useAuth();
  const canManage = user?.permissions.includes("returns.manage") ?? false;
  const [tab, setTab] = useState<"documents" | "refunds">("documents");
  const [returnType, setReturnType] = useState<ReturnType>("sales");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [lines, setLines] = useState<ReturnLine[]>([]);
  const [documents, setDocuments] = useState<ReturnDocument[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [invoiceId, setInvoiceId] = useState("");
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [refundInvoiceId, setRefundInvoiceId] = useState("");
  const [financialAccountId, setFinancialAccountId] = useState("");
  const [refundAmount, setRefundAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedInvoice = useMemo(() => invoices.find((item) => item.id === invoiceId) ?? null, [invoices, invoiceId]);
  const refundableInvoices = useMemo(() => invoices.filter((item) => Number(item.refundable) > 0), [invoices]);
  const compatibleAccounts = useMemo(() => accounts.filter((item) => item.type === accountType[paymentMethod]), [accounts, paymentMethod]);

  const load = useCallback(async (type: ReturnType) => {
    setLoading(true); setError("");
    try {
      const [invoiceRows, documentRows, refundRows, options] = await Promise.all([
        api<Invoice[]>(`/returns/invoices?return_type=${type}`), api<ReturnDocument[]>("/returns/documents?limit=250"),
        api<Refund[]>("/returns/refunds?limit=250"), api<{ accounts: Account[] }>("/returns/options"),
      ]);
      setInvoices(invoiceRows); setDocuments(documentRows); setRefunds(refundRows); setAccounts(options.accounts);
      setInvoiceId((current) => invoiceRows.some((item) => item.id === current) ? current : invoiceRows[0]?.id || "");
      setRefundInvoiceId((current) => invoiceRows.some((item) => item.id === current && Number(item.refundable) > 0) ? current : invoiceRows.find((item) => Number(item.refundable) > 0)?.id || "");
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "تعذر تحميل المرتجعات والاستردادات"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(returnType); }, [load, returnType]);
  useEffect(() => {
    if (!invoiceId) { setLines([]); return; }
    api<ReturnLine[]>(`/returns/invoices/${returnType}/${invoiceId}/lines`).then((rows) => { setLines(rows); setAmounts({}); }).catch((cause) => setError(cause instanceof ApiError ? cause.message : "تعذر تحميل بنود الفاتورة"));
  }, [invoiceId, returnType]);
  useEffect(() => {
    if (!compatibleAccounts.some((item) => item.id === financialAccountId)) setFinancialAccountId(compatibleAccounts[0]?.id || "");
  }, [compatibleAccounts, financialAccountId]);

  async function perform(action: () => Promise<unknown>, message: string) {
    setSubmitting(true); setError(""); setNotice("");
    try { await action(); setNotice(message); await load(returnType); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "تعذر إتمام العملية"); }
    finally { setSubmitting(false); }
  }

  async function createReturn(event: FormEvent) {
    event.preventDefault();
    const selectedLines = lines.flatMap((line) => {
      const value = amounts[line.source_line_id] || "0";
      return Number(value) > 0 ? [{ source_line_id: line.source_line_id, quantity: line.cost_basis === "quantity" ? value : "0", weight_kg: line.cost_basis === "weight" ? value : "0" }] : [];
    });
    await perform(() => api("/returns/documents", { method: "POST", headers: { "Idempotency-Key": `return-${crypto.randomUUID()}` }, body: JSON.stringify({ return_type: returnType, invoice_id: invoiceId, reason, lines: selectedLines }) }), "تم اعتماد المرتجع وتحديث المخزون والحسابات.");
    setReason(""); setAmounts({});
  }

  async function createRefund(event: FormEvent) {
    event.preventDefault();
    const refundType: RefundType = returnType === "sales" ? "customer_refund" : "supplier_refund";
    await perform(() => api("/returns/refunds", { method: "POST", headers: { "Idempotency-Key": `refund-${crypto.randomUUID()}` }, body: JSON.stringify({ refund_type: refundType, invoice_id: refundInvoiceId, financial_account_id: financialAccountId, amount: refundAmount, payment_method: paymentMethod, notes }) }), returnType === "sales" ? "تم رد المبلغ للعميل." : "تم استرداد المبلغ من المورد.");
    setRefundAmount(""); setNotes("");
  }

  async function reverse(kind: "documents" | "refunds", item: ReturnDocument | Refund) {
    const reversalReason = window.prompt("اكتب سبب العكس")?.trim();
    if (!reversalReason) return;
    await perform(() => api(`/returns/${kind}/${item.id}/reverse`, { method: "POST", headers: { "Idempotency-Key": `return-reversal-${crypto.randomUUID()}` }, body: JSON.stringify({ version: item.version, reason: reversalReason }) }), "تم العكس مع الاحتفاظ بالسجل التاريخي.");
  }

  const typeDocuments = documents.filter((item) => item.return_type === returnType);
  const typeRefunds = refunds.filter((item) => item.refund_type === (returnType === "sales" ? "customer_refund" : "supplier_refund"));
  return <AppShell>
    <section className="page-heading returns-heading"><div><span className="eyebrow">المرحلة التاسعة · ما بعد البيع والشراء</span><h2>المرتجعات والاستردادات</h2><p>مرتجع جزئي أو كامل مرتبط بفاتورة، مع تحديث ذري للمخزون والحسابات.</p></div><button className="secondary-button" onClick={() => void load(returnType)} disabled={loading}><RefreshCw size={17}/> تحديث</button></section>
    {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
    {notice ? <div className="alert alert--success"><Check size={17}/>{notice}</div> : null}
    <div className="sales-tabs returns-kind"><button className={returnType === "sales" ? "active" : ""} onClick={() => setReturnType("sales")}><Undo2 size={17}/> مبيعات وعملاء</button><button className={returnType === "purchase" ? "active" : ""} onClick={() => setReturnType("purchase")}><PackageOpen size={17}/> مشتريات وموردون</button></div>
    <div className="sales-tabs returns-tabs"><button className={tab === "documents" ? "active" : ""} onClick={() => setTab("documents")}><ReceiptText size={17}/> مستندات المرتجع</button><button className={tab === "refunds" ? "active" : ""} onClick={() => setTab("refunds")}><BadgeDollarSign size={17}/> المبالغ</button></div>
    {tab === "documents" ? <section className={`master-layout returns-layout ${canManage ? "" : "master-layout--single"}`}><article className="panel"><header className="panel__head"><div><h3>سجل المرتجعات</h3><p>المستندات المعتمدة والمعكوسة</p></div><span className="status-badge status-badge--active">{typeDocuments.length}</span></header><div className="return-document-list">{typeDocuments.map((item) => <article className={`return-document ${item.status === "reversed" ? "return-document--reversed" : ""}`} key={item.id}><span className="return-document__icon"><Undo2 size={19}/></span><div><strong>{item.return_number} · {item.partner_name_ar}</strong><small>{item.invoice_number} · {item.warehouse_name_ar} · {new Date(item.return_date).toLocaleDateString("ar-EG")}</small><p>{item.lines.map((line) => `${line.product_name_ar}: ${Number(line.weight_kg) > 0 ? `${line.weight_kg} كجم` : line.quantity}`).join("، ")}</p></div><b>{currency.format(Number(item.total))} ج.م</b><span className={`purchase-status purchase-status--${item.status === "posted" ? "received" : "cancelled"}`}>{item.status === "posted" ? "معتمد" : "معكوس"}</span>{canManage && item.status === "posted" ? <button className="mini-action return-reverse" onClick={() => void reverse("documents", item)} aria-label="عكس المرتجع"><RotateCcw size={15}/></button> : null}</article>)}</div></article>{canManage ? <article className="panel master-form-card"><header className="panel__head"><div><h3>مرتجع {returnType === "sales" ? "مبيعات" : "مشتريات"}</h3><p>لا يمكن تجاوز المتبقي من الفاتورة</p></div><Undo2 size={20}/></header><form className="compact-form" onSubmit={createReturn}><label>الفاتورة<select value={invoiceId} onChange={(event) => setInvoiceId(event.target.value)} required>{invoices.map((item) => <option key={item.id} value={item.id}>{item.invoice_number} · {item.partner_name_ar}</option>)}</select></label>{selectedInvoice ? <div className="return-invoice-summary"><span>الأصل <b>{currency.format(Number(selectedInvoice.original_total))}</b></span><span>مرتجع <b>{currency.format(Number(selectedInvoice.returned_total))}</b></span><span>الصافي <b>{currency.format(Number(selectedInvoice.net_total))}</b></span></div> : null}<div className="return-line-inputs">{lines.filter((line) => Number(line.cost_basis === "weight" ? line.remaining_weight_kg : line.remaining_quantity) > 0).map((line) => <label key={line.source_line_id}><span><strong>{line.product_name_ar}</strong><small>{line.product_code} · متاح {line.cost_basis === "weight" ? `${line.remaining_weight_kg} كجم` : `${line.remaining_quantity} ${line.unit}`}</small></span><input type="number" min="0" max={line.cost_basis === "weight" ? line.remaining_weight_kg : line.remaining_quantity} step="0.001" value={amounts[line.source_line_id] || ""} onChange={(event) => setAmounts((current) => ({ ...current, [line.source_line_id]: event.target.value }))} placeholder="0"/></label>)}</div><label>سبب المرتجع<textarea value={reason} onChange={(event) => setReason(event.target.value)} required/></label><button className="primary-button" disabled={submitting || !invoiceId || !reason || !Object.values(amounts).some((value) => Number(value) > 0)}><Check size={17}/> اعتماد المرتجع</button></form></article> : null}</section> : null}
    {tab === "refunds" ? <section className={`master-layout returns-layout ${canManage ? "" : "master-layout--single"}`}><article className="panel"><header className="panel__head"><div><h3>سجل المبالغ</h3><p>{returnType === "sales" ? "المردود للعملاء" : "المسترد من الموردين"}</p></div></header><div className="data-table-wrap"><table className="data-table"><thead><tr><th>الرقم</th><th>الفاتورة والطرف</th><th>الحساب</th><th>المبلغ</th><th>الحالة</th><th/></tr></thead><tbody>{typeRefunds.map((item) => <tr key={item.id}><td dir="ltr"><strong>{item.refund_number}</strong><small>{new Date(item.refund_date).toLocaleDateString("ar-EG")}</small></td><td>{item.invoice_number}<small>{item.partner_name_ar}</small></td><td>{item.financial_account_name_ar}<small>{methodLabel[item.payment_method]}</small></td><td>{currency.format(Number(item.amount))}</td><td>{item.status === "posted" ? "معتمد" : "معكوس"}</td><td>{canManage && item.status === "posted" ? <button className="mini-action" onClick={() => void reverse("refunds", item)}><RotateCcw size={14}/></button> : null}</td></tr>)}</tbody></table></div></article>{canManage ? <article className="panel master-form-card"><header className="panel__head"><div><h3>{returnType === "sales" ? "رد مبلغ للعميل" : "استرداد مبلغ من المورد"}</h3><p>لا يمكن تجاوز الرصيد القابل للاسترداد</p></div><BadgeDollarSign size={20}/></header><form className="compact-form" onSubmit={createRefund}><label>الفاتورة<select value={refundInvoiceId} onChange={(event) => setRefundInvoiceId(event.target.value)} required>{refundableInvoices.map((item) => <option key={item.id} value={item.id}>{item.invoice_number} · متاح {currency.format(Number(item.refundable))}</option>)}</select></label><div className="form-pair"><label>الطريقة<select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value as PaymentMethod)}><option value="cash">نقدي</option><option value="bank_transfer">تحويل بنكي</option><option value="cheque">شيك</option><option value="wallet">محفظة</option></select></label><label>الحساب<select value={financialAccountId} onChange={(event) => setFinancialAccountId(event.target.value)} required>{compatibleAccounts.map((item) => <option key={item.id} value={item.id}>{item.name_ar} · {item.code}</option>)}</select></label></div><label>المبلغ<input type="number" min="0.01" max={refundableInvoices.find((item) => item.id === refundInvoiceId)?.refundable} step="0.01" value={refundAmount} onChange={(event) => setRefundAmount(event.target.value)} required/></label><label>ملاحظات<textarea value={notes} onChange={(event) => setNotes(event.target.value)}/></label><button className="primary-button" disabled={submitting || !refundInvoiceId || !financialAccountId}><BadgeDollarSign size={17}/> اعتماد الحركة</button></form></article> : null}</section> : null}
  </AppShell>;
}
