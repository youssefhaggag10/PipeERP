import printBackground from "../assets/a4_invoice_background.png";

export type Company = {
  name_ar: string;
  phone: string;
  address: string;
  tax_number: string;
  currency_code: string;
};

export type DocumentLine = {
  code: string;
  name: string;
  quantity: string;
  unit: string;
  unit_price: string;
  line_total: string;
  notes: string;
  actual_weight_kg: string | null;
  price_per_kg: string | null;
};

export type PrintDocument = {
  document_type: "sales_invoice" | "weight_invoice" | "quotation";
  document_title: string;
  document_number: string;
  document_date: string;
  order_number: string;
  partner_name_ar: string;
  partner_code: string;
  partner_phone: string;
  partner_address: string;
  payment_methods: string[];
  subtotal: string;
  discount_amount: string;
  transport_amount: string;
  tax_amount: string;
  original_total: string;
  returned_total: string;
  net_total: string;
  paid: string;
  refunded: string;
  remaining: string;
  notes: string;
  valid_until: string | null;
  card_number: string;
  vehicle_number: string;
  gross_weight_kg: string;
  tare_weight_kg: string;
  net_weight_kg: string;
  lines: DocumentLine[];
  company: Company;
};

export type StatementSummary = {
  opening_balance: string;
  standard_sales_total: string;
  weight_sales_total: string;
  returns_total: string;
  receipts_total: string;
  customer_refunds_total: string;
  adjustments_total: string;
  net_movement: string;
  closing_balance: string;
};

export type Statement = {
  company: Company;
  partner_phone: string;
  detailed: boolean;
  include_drafts: boolean;
  invoice_details: Record<string, DocumentLine[]>;
  summary: StatementSummary;
  statement: {
    partner_code: string;
    partner_name_ar: string;
    date_from: string;
    date_to: string;
    opening_balance: string;
    closing_balance: string;
    lines: Array<{
      movement_date: string;
      document_number: string;
      movement_type: string;
      debit: string;
      credit: string;
      running_balance: string;
      notes: string;
    }>;
  };
};

const money = new Intl.NumberFormat("ar-EG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function chunks<T>(values: T[], size: number): T[][] {
  const pages: T[][] = [];
  for (let index = 0; index < values.length; index += size)
    pages.push(values.slice(index, index + size));
  return pages.length ? pages : [[]];
}

function companyParts(value: string) {
  const parts = value.split(/\s[-–—]\s/, 2);
  return parts.length === 2
    ? { arabic: parts[0], english: parts[1]?.toUpperCase() }
    : { arabic: value || "ثري إيه بايب", english: "3A FOR PLASTIC PRODUCTS" };
}

function dateParts(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return { date: value, time: "" };
  return {
    date: date.toLocaleDateString("ar-EG"),
    time: date.toLocaleTimeString("ar-EG", { hour: "2-digit", minute: "2-digit" }),
  };
}

function Background({ company, page, pages }: { company: Company; page: number; pages: number }) {
  const parts = companyParts(company.name_ar);
  const phones = company.phone.split(/[\n،,]/).map((value) => value.trim()).filter(Boolean);
  return (
    <>
      <img className="a4-print-background" src={printBackground} alt="" />
      <div className="a4-company-name">
        <strong>{parts.arabic}</strong>
        <b>{parts.english}</b>
        <span>لتصنيع المواسير ومنتجات البلاستيك</span>
      </div>
      <div className="a4-footer-phone">
        <strong>{phones[0] || ""}</strong>
        <span>{phones.slice(1).join(" - ")}</span>
      </div>
      <div className="a4-footer-company">
        <strong>{parts.arabic}</strong>
        <span>{parts.english}</span>
        {pages > 1 ? <small>{page} / {pages}</small> : null}
      </div>
      <div className="a4-footer-address">{company.address}</div>
    </>
  );
}

const ordinaryColumns = [
  { key: "notes", label: "ملاحظات", className: "a4-col-notes" },
  { key: "line_total", label: "الإجمالي", className: "a4-col-total" },
  { key: "unit_price", label: "سعر الوحدة", className: "a4-col-price" },
  { key: "quantity", label: "الكمية", className: "a4-col-qty" },
  { key: "unit", label: "الوحدة", className: "a4-col-unit" },
  { key: "name", label: "البيان", className: "a4-col-name" },
  { key: "serial", label: "م", className: "a4-col-serial" },
] as const;

export function BrandedDocumentPreview({ document }: { document: PrintDocument }) {
  const pages = chunks(document.lines, 6);
  const isWeight = document.document_type === "weight_invoice";
  const when = dateParts(document.document_date);
  const meta = isWeight
    ? [
        ["السيارة/الحمولة", document.vehicle_number || "—"],
        ["رقم الكارتة", document.card_number || "—"],
        ["العميل", document.partner_name_ar],
        ["الهاتف", document.partner_phone || "—"],
        ["التاريخ", when.date],
        ["رقم الأمر", document.order_number || "—"],
        ["رقم الفاتورة", document.document_number],
      ]
    : [
        ["طريقة الدفع", document.payment_methods.join("، ") || "—"],
        ["الهاتف", document.partner_phone || "—"],
        ["العميل", document.partner_name_ar],
        ["الوقت", when.time],
        ["التاريخ", when.date],
        [document.document_type === "quotation" ? "رقم العرض" : "رقم الأمر", document.order_number || "—"],
        [document.document_type === "quotation" ? "رقم المستند" : "رقم الفاتورة", document.document_number],
      ];
  return (
    <div className="a4-document print-document-target">
      {pages.map((lines, pageIndex) => {
        const isLast = pageIndex === pages.length - 1;
        const padded = [...lines, ...Array.from({ length: Math.max(0, 3 - lines.length) }, () => null)];
        return (
          <article className="a4-branded-sheet" dir="rtl" key={pageIndex}>
            <Background company={document.company} page={pageIndex + 1} pages={pages.length} />
            <h1 className="a4-document-title">{document.document_title}</h1>
            <section className={`a4-document-meta ${isWeight ? "is-weight" : ""}`} dir="ltr">
              {meta.map(([label, value]) => (
                <div key={label}>
                  <strong>{label}</strong>
                  <span dir="rtl">{value}</span>
                </div>
              ))}
            </section>
            <section className={`a4-items-grid ${isWeight ? "is-weight" : ""}`}>
              <div className="a4-items-header" dir="ltr">
                {ordinaryColumns.map((column) => (
                  <span className={column.className} key={column.key}>
                    {isWeight && column.key === "unit_price" ? "وزن الكارتة" : column.label}
                  </span>
                ))}
              </div>
              <div className="a4-items-body" style={{ gridTemplateRows: `repeat(${padded.length}, 1fr)` }}>
                {padded.map((line, rowIndex) => (
                  <div className="a4-item-row" dir="ltr" key={line ? `${line.code}-${rowIndex}` : `blank-${rowIndex}`}>
                    <span className="a4-col-notes" dir="rtl">{line?.notes || ""}</span>
                    <span className="a4-col-total">{line ? money.format(Number(line.line_total)) : ""}</span>
                    <span className="a4-col-price">{line ? (isWeight ? Number(line.actual_weight_kg || 0).toLocaleString("ar-EG", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) : money.format(Number(line.unit_price))) : ""}</span>
                    <span className="a4-col-qty">{line ? Number(line.quantity).toLocaleString("ar-EG") : ""}</span>
                    <span className="a4-col-unit" dir="rtl">{line?.unit || ""}</span>
                    <span className="a4-col-name" dir="rtl">{line ? <><strong>{line.name}</strong><small>{line.code}</small></> : null}</span>
                    <span className="a4-col-serial">{line ? pageIndex * 6 + rowIndex + 1 : ""}</span>
                  </div>
                ))}
              </div>
            </section>
            {isLast ? (
              <>
                <section className="a4-total-bands">
                  <div className="total">الإجمالي: <b>{money.format(Number(document.net_total))}</b> جنيها</div>
                  <div className="paid">تم دفع: <b>{money.format(Number(document.paid))}</b> جنيها</div>
                  <div className="remaining">إجمالي المتبقي: <b>{money.format(Number(document.remaining))}</b> جنيها</div>
                </section>
                <section className="a4-terms">
                  <h2>الشروط والملاحظات</h2>
                  <strong>جودة مضمونة<br />وثقة تدوم</strong>
                  <ol>
                    <li>السعر يشمل جودة المنتج وضمان جودة الإنتاج ودقة وسرعة التوريد والتسليم.</li>
                    <li>الأسعار غير شاملة النقل، ومتاح النقل في جميع أنحاء الجمهورية وخارجها.</li>
                    <li>{document.notes || "يتم دفع 50% والباقي عند الاستلام."}</li>
                    <li>متوفر جميع الأقطار من 25 مم إلى 800 مم.</li>
                    <li>متوفر جميع الضغوطات (4 بار، 6 بار، 10 بار).</li>
                    <li>تخضع جميع المنتجات للاختبارات اللازمة لضمان أعلى جودة قبل الوصول للعميل.</li>
                  </ol>
                </section>
              </>
            ) : (
              <div className="a4-continuation">تابع الأصناف — صفحة {pageIndex + 1} من {pages.length}</div>
            )}
          </article>
        );
      })}
    </div>
  );
}

type StatementFlatRow = {
  line: Statement["statement"]["lines"][number];
  detail: DocumentLine | null;
};

export function BrandedStatementPreview({ data }: { data: Statement }) {
  const statementRows: StatementFlatRow[] = data.statement.lines.flatMap((line) => [
    { line, detail: null },
    ...(data.invoice_details[line.document_number] || []).map((detail) => ({ line, detail })),
  ]);
  const ledgerPages = chunks(statementRows, 9);
  const totalPages = ledgerPages.length + 1;
  const summaryCards: Array<[string, string]> = [
    ["رصيد أول المدة", data.summary.opening_balance],
    ["فواتير المبيعات العادية", data.summary.standard_sales_total],
    ["فواتير المبيعات بالوزن", data.summary.weight_sales_total],
    ["مرتجعات المبيعات", data.summary.returns_total],
    ["تحصيلات العميل", data.summary.receipts_total],
    ["مبالغ مردودة للعميل", data.summary.customer_refunds_total],
    ["صافي التسويات", data.summary.adjustments_total],
    ["صافي حركة الفترة", data.summary.net_movement],
  ];
  return (
    <div className="a4-document print-document-target">
      {ledgerPages.map((rows, pageIndex) => (
        <article className="a4-branded-sheet a4-statement-sheet" dir="rtl" key={`ledger-${pageIndex}`}>
          <Background company={data.company} page={pageIndex + 1} pages={totalPages} />
          <h1 className="a4-document-title">كشف حساب عميل</h1>
          <div className="a4-statement-body">
            <section className="a4-statement-meta">
              <div><b>العميل</b><span>{data.statement.partner_name_ar}</span></div>
              <div><b>كود العميل</b><span>{data.statement.partner_code}</span></div>
              <div><b>الهاتف</b><span>{data.partner_phone || "—"}</span></div>
              <div><b>من تاريخ</b><span>{data.statement.date_from}</span></div>
              <div><b>إلى تاريخ</b><span>{data.statement.date_to}</span></div>
            </section>
            <div className="a4-opening-balance">رصيد أول المدة: {money.format(Number(data.statement.opening_balance))} جنيه — {data.detailed ? "كشف تفصيلي" : "كشف مختصر"}</div>
            <table className="a4-ledger-table">
              <thead><tr><th>التاريخ</th><th>رقم المستند</th><th>نوع المستند</th><th>البيان</th><th>مدين</th><th>دائن</th><th>الرصيد</th><th>الحالة</th></tr></thead>
              <tbody>
                {rows.map(({ line, detail }, rowIndex) => detail ? (
                  <tr className="a4-ledger-detail" key={`detail-${rowIndex}`}><td colSpan={3}>تفاصيل الفاتورة</td><td>{detail.name}<small>{detail.code} · {detail.quantity} {detail.unit}</small></td><td>{money.format(Number(detail.line_total))}</td><td>—</td><td>—</td><td>بند</td></tr>
                ) : (
                  <tr key={`${line.document_number}-${rowIndex}`}><td>{new Date(line.movement_date).toLocaleDateString("ar-EG")}</td><td>{line.document_number}</td><td>{line.movement_type}</td><td>{line.notes || line.movement_type}</td><td>{money.format(Number(line.debit))}</td><td>{money.format(Number(line.credit))}</td><td>{money.format(Number(line.running_balance))}</td><td>مرحّل</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ))}
      <article className="a4-branded-sheet a4-statement-sheet" dir="rtl">
        <Background company={data.company} page={totalPages} pages={totalPages} />
        <h1 className="a4-document-title is-summary">ملخص كشف حساب العميل</h1>
        <div className="a4-statement-body a4-summary-body">
          <section className="a4-statement-meta summary">
            <div><b>العميل</b><span>{data.statement.partner_name_ar}</span></div>
            <div><b>كود العميل</b><span>{data.statement.partner_code}</span></div>
            <div><b>الهاتف</b><span>{data.partner_phone || "—"}</span></div>
            <div><b>الفترة</b><span>{data.statement.date_from} — {data.statement.date_to}</span></div>
          </section>
          <section className="a4-summary-grid">
            {summaryCards.map(([label, value]) => <article key={label}><span>{label}</span><strong>{money.format(Number(value))} جنيه</strong></article>)}
          </section>
          <section className="a4-summary-closing"><span>الرصيد الختامي</span><strong>{money.format(Number(data.summary.closing_balance))} جنيه</strong></section>
        </div>
      </article>
    </div>
  );
}
