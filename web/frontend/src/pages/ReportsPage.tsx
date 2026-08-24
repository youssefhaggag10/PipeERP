import { BarChart3, Download, FileText, Printer, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type ReportKey = "sales" | "purchases" | "customer_balances" | "supplier_balances" | "payments" | "inventory_valuation";
type Partner = { id: string; code: string; name_ar: string; is_customer: boolean; is_supplier: boolean };
type ReportView = { report_key: ReportKey; title: string; date_from: string; date_to: string; columns: string[]; rows: Array<Record<string, string>>; summary: Record<string, string> };
type DocumentLine = { code: string; name: string; quantity: string; unit: string; unit_price: string; line_total: string; notes: string; actual_weight_kg: string | null; price_per_kg: string | null };
type PrintDocument = { document_type: "sales_invoice" | "weight_invoice" | "quotation"; document_title: string; document_number: string; document_date: string; order_number: string; partner_name_ar: string; partner_code: string; partner_phone: string; partner_address: string; payment_methods: string[]; subtotal: string; discount_amount: string; transport_amount: string; tax_amount: string; original_total: string; returned_total: string; net_total: string; paid: string; refunded: string; remaining: string; notes: string; valid_until: string | null; card_number: string; vehicle_number: string; gross_weight_kg: string; tare_weight_kg: string; net_weight_kg: string; lines: DocumentLine[]; company: Company };
type Company = { name_ar: string; phone: string; address: string; tax_number: string; currency_code: string };
type Statement = { company: Company; detailed: boolean; include_drafts: boolean; invoice_details: Record<string, DocumentLine[]>; statement: { partner_code: string; partner_name_ar: string; date_from: string; date_to: string; opening_balance: string; closing_balance: string; lines: Array<{ movement_date: string; document_number: string; movement_type: string; debit: string; credit: string; running_balance: string; notes: string }> } };
type OrderOption = { id: string; order_number: string; customer_name_ar: string; billing_method: string; invoice: { id: string; invoice_number: string; status: string } | null };
type QuoteOption = { id: string; quotation_number: string; customer_name_ar: string };

const reports: Array<{ key: ReportKey; label: string; partner: "customer" | "supplier" | "all" | "none" }> = [
  { key: "sales", label: "المبيعات", partner: "customer" },
  { key: "purchases", label: "المشتريات", partner: "supplier" },
  { key: "customer_balances", label: "أرصدة العملاء", partner: "customer" },
  { key: "supplier_balances", label: "أرصدة الموردين", partner: "supplier" },
  { key: "payments", label: "التحصيل والسداد", partner: "all" },
  { key: "inventory_valuation", label: "تقييم المخزون", partner: "none" },
];
const today = new Date().toISOString().slice(0, 10);
const monthStart = `${today.slice(0, 8)}01`;
const money = new Intl.NumberFormat("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const summaryLabels: Record<string, string> = { original: "الإجمالي الأصلي", returned: "المرتجعات", net: "الصافي", paid: "المدفوع", remaining: "المتبقي", balance: "إجمالي الرصيد", total: "إجمالي الحركات", inventory_value: "قيمة المخزون" };

function query(params: Record<string, string>) {
  const values = new URLSearchParams(Object.entries(params).filter(([, value]) => value));
  return values.toString();
}

export function ReportsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"reports" | "print">("reports");
  const [reportKey, setReportKey] = useState<ReportKey>("sales");
  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo, setDateTo] = useState(today);
  const [partnerId, setPartnerId] = useState("");
  const [partners, setPartners] = useState<Partner[]>([]);
  const [result, setResult] = useState<ReportView | null>(null);
  const [orders, setOrders] = useState<OrderOption[]>([]);
  const [quotations, setQuotations] = useState<QuoteOption[]>([]);
  const [printKind, setPrintKind] = useState<"invoice" | "quotation" | "statement">("invoice");
  const [documentId, setDocumentId] = useState("");
  const [document, setDocument] = useState<PrintDocument | null>(null);
  const [statement, setStatement] = useState<Statement | null>(null);
  const [detailedStatement, setDetailedStatement] = useState(false);
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const canSales = user?.permissions.includes("sales.read") || user?.permissions.includes("weight_sales.read");
  const canAccounts = user?.permissions.includes("accounts.read") ?? false;
  const canPrint = canSales || canAccounts;

  const selectedReport = reports.find((item) => item.key === reportKey)!;
  const filteredPartners = useMemo(() => partners.filter((item) => selectedReport.partner === "all" || (selectedReport.partner === "customer" ? item.is_customer : selectedReport.partner === "supplier" ? item.is_supplier : false)), [partners, selectedReport.partner]);
  const printOptions = printKind === "invoice" ? orders.filter((item) => item.invoice?.status === "posted") : printKind === "quotation" ? quotations : partners.filter((item) => item.is_customer);

  const loadOptions = useCallback(async () => {
    try {
      const optionRows = await api<{ partners: Partner[] }>("/reports/options");
      setPartners(optionRows.partners);
      const [orderRows, quoteRows] = canSales ? await Promise.all([api<OrderOption[]>("/sales/orders?limit=250"), user?.permissions.includes("sales.read") ? api<QuoteOption[]>("/sales/quotations?limit=250") : Promise.resolve([])]) : [[], []];
      setOrders(orderRows); setQuotations(quoteRows);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "تعذر تحميل خيارات التقارير"); }
  }, [canSales, user?.permissions]);

  useEffect(() => { void loadOptions(); }, [loadOptions]);
  useEffect(() => { if (!canSales && canAccounts) setPrintKind("statement"); }, [canAccounts, canSales]);
  useEffect(() => { setPartnerId(""); }, [reportKey]);
  useEffect(() => {
    const first = printKind === "invoice" ? orders.find((item) => item.invoice?.status === "posted")?.invoice?.id : printKind === "quotation" ? quotations[0]?.id : partners.find((item) => item.is_customer)?.id;
    setDocumentId(first || ""); setDocument(null); setStatement(null);
  }, [printKind, orders, quotations, partners]);

  async function generate() {
    setLoading(true); setError("");
    try { setResult(await api<ReportView>(`/reports/generate?${query({ report_key: reportKey, date_from: dateFrom, date_to: dateTo, partner_id: partnerId })}`)); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "تعذر إنشاء التقرير"); }
    finally { setLoading(false); }
  }

  async function preview() {
    if (!documentId) return;
    setLoading(true); setError(""); setDocument(null); setStatement(null);
    try {
      if (printKind === "statement") setStatement(await api<Statement>(`/reports/print/customer-statements/${documentId}?${query({ date_from: dateFrom, date_to: dateTo, detailed: String(detailedStatement), include_drafts: String(includeDrafts) })}`));
      else setDocument(await api<PrintDocument>(`/reports/print/${printKind === "invoice" ? "sales-invoices" : "quotations"}/${documentId}`));
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "تعذر تجهيز المستند"); }
    finally { setLoading(false); }
  }

  const exportHref = `/api/v1/reports/export.xlsx?${query({ report_key: reportKey, date_from: dateFrom, date_to: dateTo, partner_id: partnerId })}`;
  return <AppShell>
    <section className="page-heading reports-heading"><div><h2>التقارير</h2><p>تقارير محاسبية وتشغيلية مع فلترة بالعميل أو المورد وتصدير Excel.</p></div><button className="secondary-button" onClick={() => void loadOptions()}><RefreshCw size={17}/> تحديث</button></section>
    {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
    <div className="sales-tabs reports-tabs"><button className={tab === "reports" ? "active" : ""} onClick={() => setTab("reports")}><BarChart3 size={17}/> التقارير</button>{canPrint ? <button className={tab === "print" ? "active" : ""} onClick={() => setTab("print")}><Printer size={17}/> مركز طباعة A4</button> : null}</div>
    {tab === "reports" ? <>
      <section className="panel report-filters"><label>التقرير<select value={reportKey} onChange={(event) => setReportKey(event.target.value as ReportKey)}>{reports.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label><label>من<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)}/></label><label>إلى<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)}/></label>{selectedReport.partner !== "none" ? <label>الطرف<select value={partnerId} onChange={(event) => setPartnerId(event.target.value)}><option value="">الكل</option>{filteredPartners.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name_ar}</option>)}</select></label> : null}<button className="primary-button" onClick={() => void generate()} disabled={loading}><BarChart3 size={17}/> إنشاء</button>{result ? <a className="secondary-button" href={exportHref}><Download size={17}/> Excel</a> : null}</section>
      {result ? <section className="panel report-result"><header className="panel__head"><div><h3>{result.title}</h3><p>{result.date_from} — {result.date_to}</p></div><span className="status-badge status-badge--active">{result.rows.length} صف</span></header><div className="report-summary">{Object.entries(result.summary).map(([key, value]) => <span key={key}><small>{summaryLabels[key] || key}</small><strong>{value}</strong></span>)}</div><div className="data-table-wrap"><table className="data-table report-table"><thead><tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{result.rows.map((row, index) => <tr key={index}>{result.columns.map((column) => <td key={column}>{row[column] ?? "—"}</td>)}</tr>)}</tbody></table></div></section> : <section className="empty-state report-empty"><BarChart3 size={34}/><h3>اختر التقرير ثم اضغط إنشاء</h3><p>تُحسب القيم لحظيًا من المبيعات والمشتريات والخزانة والمخزون.</p></section>}
    </> : <>
      <section className="panel report-filters print-filters"><label>المستند<select value={printKind} onChange={(event) => setPrintKind(event.target.value as typeof printKind)}>{canSales ? <option value="invoice">فاتورة مبيعات / وزن</option> : null}{user?.permissions.includes("sales.read") ? <option value="quotation">عرض سعر</option> : null}{canAccounts ? <option value="statement">كشف حساب عميل</option> : null}</select></label><label>الرقم<select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>{printOptions.map((item) => { const value = "invoice" in item ? item.invoice?.id || "" : item.id; const label = "invoice" in item ? `${item.invoice?.invoice_number} · ${item.customer_name_ar}` : "quotation_number" in item ? `${item.quotation_number} · ${item.customer_name_ar}` : `${item.code} · ${item.name_ar}`; return <option key={value} value={value}>{label}</option>; })}</select></label>{printKind === "statement" ? <><label>من<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)}/></label><label>إلى<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)}/></label><label className="report-check"><input type="checkbox" checked={detailedStatement} onChange={(event) => setDetailedStatement(event.target.checked)}/> كشف تفصيلي</label><label className="report-check"><input type="checkbox" checked={includeDrafts} onChange={(event) => setIncludeDrafts(event.target.checked)}/> إظهار المسودات للمراجعة</label></> : null}<button className="primary-button" onClick={() => void preview()} disabled={loading || !documentId}><FileText size={17}/> معاينة</button>{document || statement ? <button className="secondary-button" onClick={() => window.print()}><Printer size={17}/> طباعة / PDF</button> : null}{statement ? <a className="secondary-button" href={`/api/v1/reports/export/customer-statements/${documentId}.xlsx?${query({ date_from: dateFrom, date_to: dateTo, detailed: String(detailedStatement), include_drafts: String(includeDrafts) })}`}><Download size={17}/> Excel</a> : null}</section>
      {document ? <DocumentPreview document={document}/> : null}
      {statement ? <StatementPreview data={statement}/> : null}
      {!document && !statement ? <section className="empty-state report-empty"><Printer size={34}/><h3>معاينة A4 قبل الطباعة</h3><p>اختر المستند، راجعه، ثم اطبعه أو احفظه PDF من المتصفح.</p></section> : null}
    </>}
  </AppShell>;
}

function Header({ company, title, number }: { company: Company; title: string; number: string }) { return <header className="a4-header"><div><h1>{company.name_ar}</h1><p>{company.address}</p><p className="a4-company-phones">{company.phone}{company.tax_number ? `\nضريبي ${company.tax_number}` : ""}</p></div><div><h2>{title}</h2><strong>{number}</strong></div></header>; }

function chunks<T>(values: T[], size: number): T[][] { const pages: T[][] = []; for (let index = 0; index < values.length; index += size) pages.push(values.slice(index, index + size)); return pages.length ? pages : [[]]; }

function DocumentPreview({ document }: { document: PrintDocument }) {
  const pages = chunks(document.lines, 6);
  return <div className="a4-document">{pages.map((lines, pageIndex) => { const isLast = pageIndex === pages.length - 1; return <article className="a4-sheet" dir="rtl" key={pageIndex}><Header company={document.company} title={document.document_title} number={document.document_number}/><section className="a4-meta"><span>التاريخ <b>{new Date(document.document_date).toLocaleDateString("ar-EG")}</b></span><span>العميل <b>{document.partner_name_ar}</b></span><span>الكود <b>{document.partner_code}</b></span><span>الهاتف <b>{document.partner_phone || "—"}</b></span><span>الأمر <b>{document.order_number}</b></span>{document.payment_methods.length ? <span>الدفع <b>{document.payment_methods.join("، ")}</b></span> : null}{document.valid_until ? <span>صالح حتى <b>{new Date(document.valid_until).toLocaleDateString("ar-EG")}</b></span> : null}{document.card_number ? <span>الكارتة <b>{document.card_number}</b></span> : null}{document.vehicle_number ? <span>السيارة <b>{document.vehicle_number}</b></span> : null}</section><table className="a4-table"><thead><tr><th>#</th><th>الكود والصنف</th><th>الكمية</th>{document.document_type === "weight_invoice" ? <th>الوزن الفعلي</th> : null}<th>{document.document_type === "weight_invoice" ? "سعر كجم" : "السعر"}</th><th>الإجمالي</th></tr></thead><tbody>{lines.map((line, lineIndex) => { const absoluteIndex = pageIndex * 6 + lineIndex; return <tr key={`${line.code}-${absoluteIndex}`}><td>{absoluteIndex + 1}</td><td><strong>{line.name}</strong><small>{line.code}{line.notes ? ` · ${line.notes}` : ""}</small></td><td>{line.quantity} {line.unit}</td>{document.document_type === "weight_invoice" ? <td>{line.actual_weight_kg} كجم</td> : null}<td>{money.format(Number(document.document_type === "weight_invoice" ? line.price_per_kg : line.unit_price))}</td><td>{money.format(Number(line.line_total))}</td></tr>; })}</tbody></table>{isLast && document.document_type === "weight_invoice" ? <div className="a4-weight"><span>الإجمالي القائم {document.gross_weight_kg} كجم</span><span>الفارغ {document.tare_weight_kg} كجم</span><strong>الصافي {document.net_weight_kg} كجم</strong></div> : null}{isLast ? <><footer className="a4-totals"><span>الإجمالي الأصلي <b>{money.format(Number(document.original_total))}</b></span>{Number(document.discount_amount) ? <span>الخصم <b>{money.format(Number(document.discount_amount))}</b></span> : null}{Number(document.transport_amount) ? <span>النقل <b>{money.format(Number(document.transport_amount))}</b></span> : null}{Number(document.tax_amount) ? <span>الضريبة <b>{money.format(Number(document.tax_amount))}</b></span> : null}{Number(document.returned_total) ? <span>المرتجعات <b>{money.format(Number(document.returned_total))}</b></span> : null}<span>الصافي <b>{money.format(Number(document.net_total))}</b></span><span>المدفوع <b>{money.format(Number(document.paid))}</b></span><span className="a4-due">المتبقي <b>{money.format(Number(document.remaining))} {document.company.currency_code}</b></span></footer>{document.notes ? <p className="a4-notes">ملاحظات: {document.notes}</p> : null}</> : null}<div className="a4-page-number">صفحة {pageIndex + 1} من {pages.length}</div></article>; })}</div>;
}

function StatementPreview({ data }: { data: Statement }) {
  const { statement } = data;
  const rows = statement.lines.flatMap((line) => [{ line, detail: null as DocumentLine | null }, ...(data.invoice_details[line.document_number] || []).map((detail) => ({ line, detail }))]);
  const pages = chunks(rows, 18);
  return <div className="a4-document">{pages.map((pageRows, pageIndex) => { const isLast = pageIndex === pages.length - 1; return <article className="a4-sheet" dir="rtl" key={pageIndex}><Header company={data.company} title={data.detailed ? "كشف حساب عميل تفصيلي" : "كشف حساب عميل"} number={statement.partner_code}/><section className="a4-meta"><span>العميل <b>{statement.partner_name_ar}</b></span><span>الفترة <b>{statement.date_from} — {statement.date_to}</b></span><span>رصيد أول المدة <b>{money.format(Number(statement.opening_balance))}</b></span><span>الرصيد النهائي <b>{money.format(Number(statement.closing_balance))}</b></span></section><table className="a4-table a4-statement"><thead><tr><th>التاريخ</th><th>المستند</th><th>النوع والبيان</th><th>مدين</th><th>دائن</th><th>الرصيد</th></tr></thead><tbody>{pageRows.map(({ line, detail }, rowIndex) => detail ? <tr className="a4-detail-row" key={`${pageIndex}-${rowIndex}-detail`}><td/><td/><td>↳ {detail.code} · {detail.name} · {detail.quantity} {detail.unit}</td><td/><td/><td>{money.format(Number(detail.line_total))}</td></tr> : <tr key={`${pageIndex}-${rowIndex}-${line.document_number}`}><td>{new Date(line.movement_date).toLocaleDateString("ar-EG")}</td><td>{line.document_number}</td><td><strong>{line.movement_type}</strong><small>{line.notes}</small></td><td>{money.format(Number(line.debit))}</td><td>{money.format(Number(line.credit))}</td><td>{money.format(Number(line.running_balance))}</td></tr>)}</tbody></table>{isLast ? <footer className="a4-totals"><span className="a4-due">الرصيد الختامي <b>{money.format(Number(statement.closing_balance))} {data.company.currency_code}</b></span></footer> : null}<div className="a4-page-number">صفحة {pageIndex + 1} من {pages.length}</div></article>; })}</div>;
}
