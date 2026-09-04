import {
  BarChart3,
  Download,
  FileText,
  Printer,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import {
  BrandedDocumentPreview,
  BrandedStatementPreview,
  type PrintDocument,
  type Statement,
} from "../components/A4PrintDocuments";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { printA4 } from "../lib/printA4";

type ReportKey =
  | "sales"
  | "purchases"
  | "customer_balances"
  | "supplier_balances"
  | "payments"
  | "inventory_valuation";
type Partner = {
  id: string;
  code: string;
  name_ar: string;
  is_customer: boolean;
  is_supplier: boolean;
};
type ReportView = {
  report_key: ReportKey;
  title: string;
  date_from: string;
  date_to: string;
  columns: string[];
  rows: Array<Record<string, string>>;
  summary: Record<string, string>;
};
type OrderOption = {
  id: string;
  order_number: string;
  customer_name_ar: string;
  billing_method: string;
  invoice: { id: string; invoice_number: string; status: string } | null;
};
type QuoteOption = {
  id: string;
  quotation_number: string;
  customer_name_ar: string;
};

const reports: Array<{
  key: ReportKey;
  label: string;
  partner: "customer" | "supplier" | "all" | "none";
}> = [
  { key: "sales", label: "المبيعات", partner: "customer" },
  { key: "purchases", label: "المشتريات", partner: "supplier" },
  { key: "customer_balances", label: "أرصدة العملاء", partner: "customer" },
  { key: "supplier_balances", label: "أرصدة الموردين", partner: "supplier" },
  { key: "payments", label: "التحصيل والسداد", partner: "all" },
  { key: "inventory_valuation", label: "تقييم المخزون", partner: "none" },
];
const today = new Date().toISOString().slice(0, 10);
const monthStart = `${today.slice(0, 8)}01`;
const summaryLabels: Record<string, string> = {
  original: "الإجمالي الأصلي",
  returned: "المرتجعات",
  net: "الصافي",
  paid: "المدفوع",
  remaining: "المتبقي",
  balance: "إجمالي الرصيد",
  total: "إجمالي الحركات",
  inventory_value: "قيمة المخزون",
};

function query(params: Record<string, string>) {
  const values = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value),
  );
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
  const [printKind, setPrintKind] = useState<
    "invoice" | "quotation" | "statement"
  >("invoice");
  const [documentId, setDocumentId] = useState("");
  const [document, setDocument] = useState<PrintDocument | null>(null);
  const [statement, setStatement] = useState<Statement | null>(null);
  const [detailedStatement, setDetailedStatement] = useState(false);
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const canSales =
    user?.permissions.includes("sales.read") ||
    user?.permissions.includes("weight_sales.read");
  const canAccounts = user?.permissions.includes("accounts.read") ?? false;
  const canPrint = canSales || canAccounts;

  const selectedReport = reports.find((item) => item.key === reportKey)!;
  const filteredPartners = useMemo(
    () =>
      partners.filter(
        (item) =>
          selectedReport.partner === "all" ||
          (selectedReport.partner === "customer"
            ? item.is_customer
            : selectedReport.partner === "supplier"
              ? item.is_supplier
              : false),
      ),
    [partners, selectedReport.partner],
  );
  const printOptions =
    printKind === "invoice"
      ? orders.filter((item) => item.invoice?.status === "posted")
      : printKind === "quotation"
        ? quotations
        : partners.filter((item) => item.is_customer);

  const loadOptions = useCallback(async () => {
    try {
      const optionRows = await api<{ partners: Partner[] }>("/reports/options");
      setPartners(optionRows.partners);
      const [orderRows, quoteRows] = canSales
        ? await Promise.all([
            api<OrderOption[]>("/sales/orders?limit=250"),
            user?.permissions.includes("sales.read")
              ? api<QuoteOption[]>("/sales/quotations?limit=250")
              : Promise.resolve([]),
          ])
        : [[], []];
      setOrders(orderRows);
      setQuotations(quoteRows);
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "تعذر تحميل خيارات التقارير",
      );
    }
  }, [canSales, user?.permissions]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);
  useEffect(() => {
    if (!canSales && canAccounts) setPrintKind("statement");
  }, [canAccounts, canSales]);
  useEffect(() => {
    setPartnerId("");
  }, [reportKey]);
  useEffect(() => {
    const first =
      printKind === "invoice"
        ? orders.find((item) => item.invoice?.status === "posted")?.invoice?.id
        : printKind === "quotation"
          ? quotations[0]?.id
          : partners.find((item) => item.is_customer)?.id;
    setDocumentId(first || "");
    setDocument(null);
    setStatement(null);
  }, [printKind, orders, quotations, partners]);

  async function generate() {
    setLoading(true);
    setError("");
    try {
      setResult(
        await api<ReportView>(
          `/reports/generate?${query({ report_key: reportKey, date_from: dateFrom, date_to: dateTo, partner_id: partnerId })}`,
        ),
      );
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "تعذر إنشاء التقرير",
      );
    } finally {
      setLoading(false);
    }
  }

  async function preview() {
    if (!documentId) return;
    setLoading(true);
    setError("");
    setDocument(null);
    setStatement(null);
    try {
      if (printKind === "statement")
        setStatement(
          await api<Statement>(
            `/reports/print/customer-statements/${documentId}?${query({ date_from: dateFrom, date_to: dateTo, detailed: String(detailedStatement), include_drafts: String(includeDrafts) })}`,
          ),
        );
      else
        setDocument(
          await api<PrintDocument>(
            `/reports/print/${printKind === "invoice" ? "sales-invoices" : "quotations"}/${documentId}`,
          ),
        );
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "تعذر تجهيز المستند",
      );
    } finally {
      setLoading(false);
    }
  }

  const exportHref = `/api/v1/reports/export.xlsx?${query({ report_key: reportKey, date_from: dateFrom, date_to: dateTo, partner_id: partnerId })}`;
  return (
    <AppShell>
      <section className="page-heading reports-heading">
        <div>
          <h2>التقارير</h2>
          <p>
            تقارير محاسبية وتشغيلية مع فلترة بالعميل أو المورد وتصدير Excel.
          </p>
        </div>
        <button className="secondary-button" onClick={() => void loadOptions()}>
          <RefreshCw size={17} /> تحديث
        </button>
      </section>
      {error ? (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      ) : null}
      <div className="sales-tabs reports-tabs">
        <button
          className={tab === "reports" ? "active" : ""}
          onClick={() => setTab("reports")}
        >
          <BarChart3 size={17} /> التقارير
        </button>
        {canPrint ? (
          <button
            className={tab === "print" ? "active" : ""}
            onClick={() => setTab("print")}
          >
            <Printer size={17} /> مركز طباعة A4
          </button>
        ) : null}
      </div>
      {tab === "reports" ? (
        <>
          <section className="panel report-filters">
            <label>
              التقرير
              <select
                value={reportKey}
                onChange={(event) =>
                  setReportKey(event.target.value as ReportKey)
                }
              >
                {reports.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              من
              <input
                type="date"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
              />
            </label>
            <label>
              إلى
              <input
                type="date"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
              />
            </label>
            {selectedReport.partner !== "none" ? (
              <label>
                الطرف
                <select
                  value={partnerId}
                  onChange={(event) => setPartnerId(event.target.value)}
                >
                  <option value="">الكل</option>
                  {filteredPartners.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.code} · {item.name_ar}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <button
              className="primary-button"
              onClick={() => void generate()}
              disabled={loading}
            >
              <BarChart3 size={17} /> إنشاء
            </button>
            {result ? (
              <a className="secondary-button" href={exportHref}>
                <Download size={17} /> Excel
              </a>
            ) : null}
          </section>
          {result ? (
            <section className="panel report-result">
              <header className="panel__head">
                <div>
                  <h3>{result.title}</h3>
                  <p>
                    {result.date_from} — {result.date_to}
                  </p>
                </div>
                <span className="status-badge status-badge--active">
                  {result.rows.length} صف
                </span>
              </header>
              <div className="report-summary">
                {Object.entries(result.summary).map(([key, value]) => (
                  <span key={key}>
                    <small>{summaryLabels[key] || key}</small>
                    <strong>{value}</strong>
                  </span>
                ))}
              </div>
              <div className="data-table-wrap">
                <table className="data-table report-table">
                  <thead>
                    <tr>
                      {result.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, index) => (
                      <tr key={index}>
                        {result.columns.map((column) => (
                          <td key={column}>{row[column] ?? "—"}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : (
            <section className="empty-state report-empty">
              <BarChart3 size={34} />
              <h3>اختر التقرير ثم اضغط إنشاء</h3>
              <p>
                تُحسب القيم لحظيًا من المبيعات والمشتريات والخزانة والمخزون.
              </p>
            </section>
          )}
        </>
      ) : (
        <>
          <section className="panel report-filters print-filters">
            <label>
              المستند
              <select
                value={printKind}
                onChange={(event) =>
                  setPrintKind(event.target.value as typeof printKind)
                }
              >
                {canSales ? (
                  <option value="invoice">فاتورة مبيعات / وزن</option>
                ) : null}
                {user?.permissions.includes("sales.read") ? (
                  <option value="quotation">عرض سعر</option>
                ) : null}
                {canAccounts ? (
                  <option value="statement">كشف حساب عميل</option>
                ) : null}
              </select>
            </label>
            <label>
              الرقم
              <select
                value={documentId}
                onChange={(event) => setDocumentId(event.target.value)}
              >
                {printOptions.map((item) => {
                  const value =
                    "invoice" in item ? item.invoice?.id || "" : item.id;
                  const label =
                    "invoice" in item
                      ? `${item.invoice?.invoice_number} · ${item.customer_name_ar}`
                      : "quotation_number" in item
                        ? `${item.quotation_number} · ${item.customer_name_ar}`
                        : `${item.code} · ${item.name_ar}`;
                  return (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  );
                })}
              </select>
            </label>
            {printKind === "statement" ? (
              <>
                <label>
                  من
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(event) => setDateFrom(event.target.value)}
                  />
                </label>
                <label>
                  إلى
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(event) => setDateTo(event.target.value)}
                  />
                </label>
                <label className="report-check">
                  <input
                    type="checkbox"
                    checked={detailedStatement}
                    onChange={(event) =>
                      setDetailedStatement(event.target.checked)
                    }
                  />{" "}
                  كشف تفصيلي
                </label>
                <label className="report-check">
                  <input
                    type="checkbox"
                    checked={includeDrafts}
                    onChange={(event) => setIncludeDrafts(event.target.checked)}
                  />{" "}
                  إظهار المسودات للمراجعة
                </label>
              </>
            ) : null}
            <button
              className="primary-button"
              onClick={() => void preview()}
              disabled={loading || !documentId}
            >
              <FileText size={17} /> معاينة
            </button>
            {document || statement ? (
              <button
                className="secondary-button"
                onClick={printA4}
              >
                <Printer size={17} /> A4 / PDF
              </button>
            ) : null}
            {statement ? (
              <a
                className="secondary-button"
                href={`/api/v1/reports/export/customer-statements/${documentId}.xlsx?${query({ date_from: dateFrom, date_to: dateTo, detailed: String(detailedStatement), include_drafts: String(includeDrafts) })}`}
              >
                <Download size={17} /> Excel
              </a>
            ) : null}
          </section>
          {document ? <BrandedDocumentPreview document={document} /> : null}
          {statement ? <BrandedStatementPreview data={statement} /> : null}
          {!document && !statement ? (
            <section className="empty-state report-empty">
              <Printer size={34} />
              <h3>معاينة A4 قبل الطباعة</h3>
              <p>اختر المستند، راجعه، ثم اطبعه أو احفظه PDF من المتصفح.</p>
            </section>
          ) : null}
        </>
      )}
    </AppShell>
  );
}
