import {
  BadgeDollarSign,
  Banknote,
  Building2,
  Check,
  CircleDollarSign,
  FileClock,
  Landmark,
  Plus,
  RefreshCw,
  ReceiptText,
  RotateCcw,
  Scale,
  UsersRound,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";
import { clientId } from "../lib/clientId";
import { ReturnsWorkspace } from "./ReturnsPage";

type Tab =
  | "summary"
  | "payments"
  | "accounts"
  | "partners"
  | "sales-invoices"
  | "purchase-invoices"
  | "returns";
type TransactionType = "customer_receipt" | "supplier_payment";
type PaymentMethod = "cash" | "bank_transfer" | "cheque" | "wallet";
type PartnerType = "customer" | "supplier";
type Partner = {
  id: string;
  code: string;
  name_ar: string;
  is_customer: boolean;
  is_supplier: boolean;
};
type FinancialAccount = {
  id: string;
  code: string;
  name_ar: string;
  account_type: "cash" | "bank" | "wallet" | "other";
  opening_balance: string;
  current_balance: string;
  is_default: boolean;
  is_active: boolean;
  notes: string;
  version: number;
};
type Allocation = {
  invoice_id: string;
  invoice_number: string;
  amount: string;
};
type Payment = {
  id: string;
  transaction_number: string;
  transaction_date: string;
  transaction_type: TransactionType;
  partner_name_ar: string;
  financial_account_name_ar: string;
  amount: string;
  payment_method: PaymentMethod;
  reference_type: "sale" | "purchase" | null;
  reference_id: string | null;
  allocated_amount: string;
  unallocated_amount: string;
  status: "posted" | "reversed";
  notes: string;
  reversal_reason: string;
  allocations: Allocation[];
};
type OpenInvoice = {
  id: string;
  invoice_number: string;
  invoice_date: string;
  invoice_total: string;
  paid: string;
  remaining: string;
};
type AccountInvoice = {
  id: string;
  invoice_number: string;
  invoice_type: "sales" | "purchase";
  invoice_date: string;
  order_number: string;
  partner_id: string;
  partner_name_ar: string;
  original_total: string;
  returned_total: string;
  net_total: string;
  paid: string;
  refunded: string;
  remaining: string;
  refundable: string;
  return_status: "none" | "partial" | "full";
  partner_phone: string;
  payment_methods: PaymentMethod[];
  invoice_status: string;
  delivery_return_status: string;
  payment_status: "unpaid" | "partial" | "paid";
};
type OpenOrder = {
  id: string;
  order_number: string;
  order_date: string;
  status: string;
  total: string;
  paid: string;
  remaining: string;
  reference_type: "sale" | "purchase";
};
type PartnerBalance = {
  partner_id: string;
  partner_code: string;
  partner_name_ar: string;
  partner_type: PartnerType;
  opening_balance: string;
  invoices_total: string;
  returns_total: string;
  paid_total: string;
  refunds_total: string;
  advances: string;
  adjustments_total: string;
  balance: string;
};
type OpeningBalance = {
  id: string;
  entry_number: string;
  entry_date: string;
  partner_name_ar: string;
  nature: "debit" | "credit";
  amount: string;
  status: "posted" | "reversed" | "reversal";
};
type CustomerAdjustment = {
  id: string;
  adjustment_number: string;
  adjustment_date: string;
  customer_name_ar: string;
  adjustment_type: "debit" | "credit";
  amount: string;
  status: "posted" | "reversed";
  notes: string;
};
type Summary = {
  financial_balance: string;
  receivables: string;
  payables: string;
  customer_receipts: string;
  supplier_payments: string;
  sales_returns: string;
  purchase_returns: string;
  customer_refunds: string;
  supplier_refunds: string;
  customer_advances: string;
  supplier_advances: string;
};
type Statement = {
  partner_name_ar: string;
  partner_type: PartnerType;
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

const currency = new Intl.NumberFormat("ar-EG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const methodLabels: Record<PaymentMethod, string> = {
  cash: "نقدي",
  bank_transfer: "تحويل بنكي",
  cheque: "شيك",
  wallet: "محفظة إلكترونية",
};
const typeLabels: Record<TransactionType, string> = {
  customer_receipt: "تحصيل عميل",
  supplier_payment: "سداد مورد",
};

export function TreasuryPage() {
  const { user } = useAuth();
  const canManage = user?.permissions.includes("accounts.manage") ?? false;
  const canReturns = user?.permissions.includes("returns.read") ?? false;
  const [tab, setTab] = useState<Tab>("summary");
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [salesInvoices, setSalesInvoices] = useState<AccountInvoice[]>([]);
  const [purchaseInvoices, setPurchaseInvoices] = useState<AccountInvoice[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [customerBalances, setCustomerBalances] = useState<PartnerBalance[]>(
    [],
  );
  const [supplierBalances, setSupplierBalances] = useState<PartnerBalance[]>(
    [],
  );
  const [openingBalances, setOpeningBalances] = useState<OpeningBalance[]>([]);
  const [customerAdjustments, setCustomerAdjustments] = useState<
    CustomerAdjustment[]
  >([]);
  const [summary, setSummary] = useState<Summary>({
    financial_balance: "0",
    receivables: "0",
    payables: "0",
    customer_receipts: "0",
    supplier_payments: "0",
    sales_returns: "0",
    purchase_returns: "0",
    customer_refunds: "0",
    supplier_refunds: "0",
    customer_advances: "0",
    supplier_advances: "0",
  });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [transactionType, setTransactionType] =
    useState<TransactionType>("customer_receipt");
  const [partnerId, setPartnerId] = useState("");
  const [financialAccountId, setFinancialAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("cash");
  const [paymentNotes, setPaymentNotes] = useState("");
  const [linkMode, setLinkMode] = useState<"advance" | "order" | "invoices">(
    "advance",
  );
  const [orderId, setOrderId] = useState("");
  const [openOrders, setOpenOrders] = useState<OpenOrder[]>([]);
  const [openInvoices, setOpenInvoices] = useState<OpenInvoice[]>([]);
  const [allocationAmounts, setAllocationAmounts] = useState<
    Record<string, string>
  >({});
  const [invoicePaymentTarget, setInvoicePaymentTarget] = useState<AccountInvoice | null>(null);
  const [returnTarget, setReturnTarget] = useState<AccountInvoice | null>(null);
  const [invoiceSearch, setInvoiceSearch] = useState("");

  const [accountForm, setAccountForm] = useState({
    code: "",
    name_ar: "",
    account_type: "cash",
    opening_balance: "0",
    is_default: false,
    is_active: true,
    notes: "",
  });
  const [editingAccount, setEditingAccount] = useState<FinancialAccount | null>(
    null,
  );
  const [adjustmentForm, setAdjustmentForm] = useState({
    financial_account_id: "",
    target_balance: "",
    notes: "",
  });
  const [partnerType, setPartnerType] = useState<PartnerType>("customer");
  const [openingForm, setOpeningForm] = useState({
    partner_id: "",
    nature: "debit",
    amount: "",
    entry_date: new Date().toISOString().slice(0, 10),
    notes: "",
  });
  const [customerAdjustmentForm, setCustomerAdjustmentForm] = useState({
    customer_id: "",
    adjustment_type: "debit",
    amount: "",
    notes: "",
  });
  const [statementPartnerId, setStatementPartnerId] = useState("");
  const [statementFrom, setStatementFrom] = useState(
    `${new Date().getFullYear()}-01-01`,
  );
  const [statementTo, setStatementTo] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [statement, setStatement] = useState<Statement | null>(null);

  const availablePartners = useMemo(
    () =>
      partners.filter((item) =>
        transactionType === "customer_receipt"
          ? item.is_customer
          : item.is_supplier,
      ),
    [partners, transactionType],
  );
  const statementPartners = useMemo(
    () =>
      partners.filter((item) =>
        partnerType === "customer" ? item.is_customer : item.is_supplier,
      ),
    [partners, partnerType],
  );
  const compatibleAccounts = useMemo(
    () =>
      accounts.filter(
        (item) =>
          item.is_active &&
          {
            cash: "cash",
            bank_transfer: "bank",
            cheque: "bank",
            wallet: "wallet",
          }[paymentMethod] === item.account_type,
      ),
    [accounts, paymentMethod],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [
        accountRows,
        paymentRows,
        treasuryOptions,
        customerRows,
        supplierRows,
        openingRows,
        adjustmentRows,
        summaryRow,
        salesInvoiceRows,
        purchaseInvoiceRows,
      ] = await Promise.all([
        api<FinancialAccount[]>(
          "/accounts/financial-accounts?include_inactive=true",
        ),
        api<Payment[]>("/accounts/payments?limit=250"),
        api<{ partners: Partner[] }>("/accounts/options"),
        api<PartnerBalance[]>(
          "/accounts/partner-balances?partner_type=customer",
        ),
        api<PartnerBalance[]>(
          "/accounts/partner-balances?partner_type=supplier",
        ),
        api<OpeningBalance[]>("/accounts/opening-balances"),
        api<CustomerAdjustment[]>("/accounts/customer-adjustments"),
        api<Summary>("/accounts/summary"),
        api<AccountInvoice[]>("/accounts/invoices?invoice_type=sales"),
        api<AccountInvoice[]>("/accounts/invoices?invoice_type=purchase"),
      ]);
      const partnerRows = treasuryOptions.partners;
      setAccounts(accountRows);
      setPayments(paymentRows);
      setPartners(partnerRows);
      setCustomerBalances(customerRows);
      setSupplierBalances(supplierRows);
      setOpeningBalances(openingRows);
      setCustomerAdjustments(adjustmentRows);
      setSummary(summaryRow);
      setSalesInvoices(salesInvoiceRows);
      setPurchaseInvoices(purchaseInvoiceRows);
      setPartnerId(
        (current) =>
          current || partnerRows.find((item) => item.is_customer)?.id || "",
      );
      setFinancialAccountId(
        (current) =>
          current ||
          accountRows.find((item) => item.is_default)?.id ||
          accountRows[0]?.id ||
          "",
      );
      setAdjustmentForm((current) => ({
        ...current,
        financial_account_id:
          current.financial_account_id || accountRows[0]?.id || "",
      }));
      setOpeningForm((current) => ({
        ...current,
        partner_id:
          current.partner_id ||
          partnerRows.find((item) => item.is_customer)?.id ||
          "",
      }));
      setCustomerAdjustmentForm((current) => ({
        ...current,
        customer_id:
          current.customer_id ||
          partnerRows.find((item) => item.is_customer)?.id ||
          "",
      }));
      setStatementPartnerId(
        (current) =>
          current || partnerRows.find((item) => item.is_customer)?.id || "",
      );
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "تعذر تحميل الخزينة والحسابات",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    const next = availablePartners[0]?.id || "";
    if (!availablePartners.some((item) => item.id === partnerId))
      setPartnerId(next);
  }, [availablePartners, partnerId]);
  useEffect(() => {
    const next = compatibleAccounts[0]?.id || "";
    if (!compatibleAccounts.some((item) => item.id === financialAccountId))
      setFinancialAccountId(next);
  }, [compatibleAccounts, financialAccountId]);
  useEffect(() => {
    if (!partnerId) {
      setOpenInvoices([]);
      setOpenOrders([]);
      return;
    }
    const query = new URLSearchParams({
      transaction_type: transactionType,
      partner_id: partnerId,
    });
    Promise.all([
      api<OpenInvoice[]>(`/accounts/open-invoices?${query}`),
      api<OpenOrder[]>(`/accounts/open-orders?${query}`),
    ])
      .then(([invoices, orders]) => {
        setOpenInvoices(invoices);
        setOpenOrders(orders);
        setOrderId(orders[0]?.id || "");
        setAllocationAmounts({});
      })
      .catch((reason) =>
        setError(
          reason instanceof ApiError
            ? reason.message
            : "تعذر تحميل المستندات المفتوحة",
        ),
      );
  }, [partnerId, transactionType]);
  useEffect(() => {
    if (!invoicePaymentTarget) return;
    if (!openInvoices.some((item) => item.id === invoicePaymentTarget.id)) return;
    setLinkMode("invoices");
    setAmount(invoicePaymentTarget.remaining);
    setAllocationAmounts({
      [invoicePaymentTarget.id]: invoicePaymentTarget.remaining,
    });
    setInvoicePaymentTarget(null);
  }, [invoicePaymentTarget, openInvoices]);

  function showError(reason: unknown, fallback: string) {
    setError(reason instanceof ApiError ? reason.message : fallback);
  }
  async function perform(action: () => Promise<unknown>, message: string) {
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
      await load();
    } catch (reason) {
      showError(reason, "تعذر إتمام العملية");
    } finally {
      setSubmitting(false);
    }
  }

  async function postPayment(event: FormEvent) {
    event.preventDefault();
    const allocations =
      linkMode === "invoices"
        ? Object.entries(allocationAmounts)
            .filter(([, value]) => Number(value) > 0)
            .map(([invoice_id, value]) => ({ invoice_id, amount: value }))
        : [];
    const selectedOrder = openOrders.find((item) => item.id === orderId);
    await perform(
      () =>
        api("/accounts/payments", {
          method: "POST",
          headers: { "Idempotency-Key": clientId("payment") },
          body: JSON.stringify({
            transaction_type: transactionType,
            partner_id: partnerId,
            financial_account_id: financialAccountId,
            amount,
            payment_method: paymentMethod,
            reference_type:
              linkMode === "order" ? selectedOrder?.reference_type : null,
            reference_id: linkMode === "order" ? orderId : null,
            allocations,
            notes: paymentNotes,
          }),
        }),
      `تم تسجيل ${typeLabels[transactionType]} بنجاح.`,
    );
    setAmount("");
    setPaymentNotes("");
    setAllocationAmounts({});
  }

  async function saveAccount(event: FormEvent) {
    event.preventDefault();
    await perform(
      () =>
        api(
          editingAccount
            ? `/accounts/financial-accounts/${editingAccount.id}`
            : "/accounts/financial-accounts",
          {
            method: editingAccount ? "PUT" : "POST",
            body: JSON.stringify({
              ...accountForm,
              ...(editingAccount ? { version: editingAccount.version } : {}),
            }),
          },
        ),
      editingAccount ? "تم تحديث الحساب المالي." : "تم إنشاء الحساب المالي.",
    );
    setEditingAccount(null);
    setAccountForm({
      code: "",
      name_ar: "",
      account_type: "cash",
      opening_balance: "0",
      is_default: false,
      is_active: true,
      notes: "",
    });
  }
  function editAccount(item: FinancialAccount) {
    setEditingAccount(item);
    setAccountForm({
      code: item.code,
      name_ar: item.name_ar,
      account_type: item.account_type,
      opening_balance: item.opening_balance,
      is_default: item.is_default,
      is_active: item.is_active,
      notes: item.notes,
    });
  }
  async function postAdjustment(event: FormEvent) {
    event.preventDefault();
    await perform(
      () =>
        api("/accounts/financial-adjustments", {
          method: "POST",
          headers: { "Idempotency-Key": clientId("adjustment") },
          body: JSON.stringify(adjustmentForm),
        }),
      "تمت تسوية الرصيد مع حفظ الأثر.",
    );
    setAdjustmentForm((current) => ({
      ...current,
      target_balance: "",
      notes: "",
    }));
  }
  async function postOpening(event: FormEvent) {
    event.preventDefault();
    await perform(
      () =>
        api("/accounts/opening-balances", {
          method: "POST",
          body: JSON.stringify(openingForm),
        }),
      "تم تسجيل الرصيد الافتتاحي دون التأثير على الخزينة.",
    );
    setOpeningForm((current) => ({ ...current, amount: "", notes: "" }));
  }
  async function postCustomerAdjustment(event: FormEvent) {
    event.preventDefault();
    await perform(
      () =>
        api("/accounts/customer-adjustments", {
          method: "POST",
          body: JSON.stringify(customerAdjustmentForm),
        }),
      "تم تسجيل تسوية حساب العميل.",
    );
    setCustomerAdjustmentForm((current) => ({
      ...current,
      amount: "",
      notes: "",
    }));
  }
  async function reverse(
    path: string,
    id: string,
    label: string,
    needsKey = true,
  ) {
    const reason = window.prompt(`اكتب سبب عكس ${label}`)?.trim();
    if (!reason) return;
    await perform(
      () =>
        api(`${path}/${id}/reversal`, {
          method: "POST",
          headers: needsKey
            ? { "Idempotency-Key": clientId("reversal") }
            : undefined,
          body: JSON.stringify({ reason }),
        }),
      `تم عكس ${label} مع الاحتفاظ بالسجل.`,
    );
  }
  async function loadStatement(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      setStatement(
        await api<Statement>(
          `/accounts/partners/${statementPartnerId}/statement?date_from=${statementFrom}&date_to=${statementTo}&partner_type=${partnerType}`,
        ),
      );
    } catch (reason) {
      showError(reason, "تعذر إنشاء كشف الحساب");
    }
  }

  function payInvoice(item: AccountInvoice) {
    setTransactionType(item.invoice_type === "sales" ? "customer_receipt" : "supplier_payment");
    setPartnerId(item.partner_id);
    setInvoicePaymentTarget(item);
    setTab("payments");
  }

  function returnInvoice(item: AccountInvoice) {
    setReturnTarget(item);
    setTab("returns");
  }

  const balances =
    partnerType === "customer" ? customerBalances : supplierBalances;
  const displayedInvoices = (
    tab === "sales-invoices" ? salesInvoices : purchaseInvoices
  ).filter((item) =>
    [
      item.invoice_number,
      item.order_number,
      item.partner_name_ar,
      item.partner_phone,
      (item.payment_methods ?? []).join(" "),
      item.delivery_return_status,
    ]
      .join(" ")
      .toLocaleLowerCase("ar")
      .includes(invoiceSearch.trim().toLocaleLowerCase("ar")),
  );
  return (
    <AppShell>
      <section className="page-heading treasury-heading">
        <div>
          <h2>الحسابات</h2>
          <p>متابعة الأرصدة والفواتير والتحصيلات والسداد والمديونيات.</p>
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
      {tab === "summary" ? <section className="inventory-stats treasury-stats">
        <article>
          <span className="inventory-stat__icon">
            <Banknote size={20} />
          </span>
          <span>
            <small>إجمالي فواتير المبيعات</small>
            <strong>
              {currency.format(salesInvoices.reduce((total, item) => total + Number(item.original_total), 0))} <em>ج.م</em>
            </strong>
          </span>
        </article>
        <article>
          <span className="inventory-stat__icon inventory-stat__icon--blue">
            <UsersRound size={20} />
          </span>
          <span>
            <small>تحصيلات العملاء</small>
            <strong>
              {currency.format(Number(summary.customer_receipts))} <em>ج.م</em>
            </strong>
          </span>
        </article>
        <article>
          <span className="inventory-stat__icon inventory-stat__icon--amber">
            <Building2 size={20} />
          </span>
          <span>
            <small>دفعات مقدمة من العملاء</small>
            <strong>
              {currency.format(Number(summary.customer_advances))} <em>ج.م</em>
            </strong>
          </span>
        </article>
        <article>
          <span className="inventory-stat__icon inventory-stat__icon--violet">
            <FileClock size={20} />
          </span>
          <span>
            <small>مديونيات العملاء</small>
            <strong>
              {currency.format(Number(summary.receivables))} <em>ج.م</em>
            </strong>
          </span>
        </article>
        <article><span className="inventory-stat__icon"><ReceiptText size={20}/></span><span><small>إجمالي فواتير المشتريات</small><strong>{currency.format(purchaseInvoices.reduce((total, item) => total + Number(item.original_total), 0))} <em>ج.م</em></strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--blue"><CircleDollarSign size={20}/></span><span><small>مدفوعات الموردين</small><strong>{currency.format(Number(summary.supplier_payments))} <em>ج.م</em></strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--amber"><FileClock size={20}/></span><span><small>دفعات مقدمة للموردين</small><strong>{currency.format(Number(summary.supplier_advances))} <em>ج.م</em></strong></span></article>
        <article><span className="inventory-stat__icon inventory-stat__icon--violet"><Building2 size={20}/></span><span><small>مديونيات الموردين</small><strong>{currency.format(Number(summary.payables))} <em>ج.م</em></strong></span></article>
      </section> : null}
      <div className="sales-tabs treasury-tabs" role="tablist">
        <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}><Scale size={17}/> الملخص</button>
        <button
          className={tab === "payments" ? "active" : ""}
          onClick={() => setTab("payments")}
        >
          <CircleDollarSign size={17} /> التحصيل والسداد
        </button>
        <button
          className={tab === "accounts" ? "active" : ""}
          onClick={() => setTab("accounts")}
        >
          <Landmark size={17} /> الخزائن والبنوك
        </button>
        <button
          className={tab === "partners" ? "active" : ""}
          onClick={() => setTab("partners")}
        >
          <Scale size={17} /> أرصدة وكشوف
        </button>
        <button
          className={tab === "sales-invoices" ? "active" : ""}
          onClick={() => setTab("sales-invoices")}
        >
          <ReceiptText size={17} /> فواتير المبيعات
        </button>
        <button
          className={tab === "purchase-invoices" ? "active" : ""}
          onClick={() => setTab("purchase-invoices")}
        >
          <ReceiptText size={17} /> فواتير المشتريات
        </button>
        {canReturns ? (
          <button
            className={tab === "returns" ? "active" : ""}
            onClick={() => setTab("returns")}
          >
            <ReceiptText size={17} /> المرتجعات والاستردادات
          </button>
        ) : null}
      </div>

      {tab === "payments" ? (
        <section
          className={`master-layout treasury-layout ${canManage ? "" : "master-layout--single"}`}
        >
          <article className="panel">
            <header className="panel__head">
              <div>
                <h3>دفتر التحصيل والسداد</h3>
                <p>الحركات المعتمدة والمعكوسة وتوزيع الفواتير</p>
              </div>
              <span className="status-badge status-badge--active">
                {payments.length}
              </span>
            </header>
            {payments.length ? (
              <div className="data-table-wrap">
                <table className="data-table treasury-table">
                  <thead>
                    <tr>
                      <th>الرقم</th>
                      <th>الحركة</th>
                      <th>الطرف</th>
                      <th>الحساب</th>
                      <th>المبلغ</th>
                      <th>المخصص</th>
                      <th>الحالة</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {payments.map((item) => (
                      <tr key={item.id}>
                        <td dir="ltr">
                          <strong>{item.transaction_number}</strong>
                          <small>
                            {new Date(item.transaction_date).toLocaleDateString(
                              "ar-EG",
                            )}
                          </small>
                        </td>
                        <td>
                          {typeLabels[item.transaction_type]}
                          <small>{methodLabels[item.payment_method]}</small>
                        </td>
                        <td>{item.partner_name_ar}</td>
                        <td>{item.financial_account_name_ar}</td>
                        <td
                          className={
                            item.transaction_type === "customer_receipt"
                              ? "movement-positive"
                              : "movement-negative"
                          }
                        >
                          {currency.format(Number(item.amount))}
                        </td>
                        <td>
                          {currency.format(Number(item.allocated_amount))}
                          <small>
                            {Number(item.unallocated_amount)
                              ? `مقدم ${currency.format(Number(item.unallocated_amount))}`
                              : "موزع بالكامل"}
                          </small>
                        </td>
                        <td>
                          <span
                            className={`purchase-status purchase-status--${item.status === "posted" ? "received" : "cancelled"}`}
                          >
                            {item.status === "posted" ? "معتمد" : "معكوس"}
                          </span>
                        </td>
                        <td>
                          {canManage && item.status === "posted" ? (
                            <button
                              className="mini-action"
                              onClick={() =>
                                void reverse(
                                  "/accounts/payments",
                                  item.id,
                                  "الحركة المالية",
                                )
                              }
                              aria-label="عكس الحركة"
                            >
                              <RotateCcw size={14} />
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <span className="empty-state__icon">
                  <CircleDollarSign size={27} />
                </span>
                <h4>لا توجد حركات مالية</h4>
                <p>ابدأ بأول تحصيل أو سداد من النموذج.</p>
              </div>
            )}
          </article>
          {canManage ? (
            <article className="panel master-form-card treasury-form-card">
              <header className="panel__head">
                <div>
                  <h3>حركة مالية جديدة</h3>
                  <p>يمكن تركها مقدمة أو ربطها بأمر أو توزيعها</p>
                </div>
                <Plus size={20} />
              </header>
              <form
                className="compact-form treasury-payment-form"
                onSubmit={postPayment}
              >
                <div className="form-pair">
                  <label>
                    نوع الحركة
                    <select
                      value={transactionType}
                      onChange={(event) => {
                        setTransactionType(
                          event.target.value as TransactionType,
                        );
                        setLinkMode("advance");
                      }}
                    >
                      <option value="customer_receipt">تحصيل من عميل</option>
                      <option value="supplier_payment">سداد لمورد</option>
                    </select>
                  </label>
                  <label>
                    {transactionType === "customer_receipt"
                      ? "العميل"
                      : "المورد"}
                    <select
                      value={partnerId}
                      onChange={(event) => setPartnerId(event.target.value)}
                      required
                    >
                      {availablePartners.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name_ar} · {item.code}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="form-pair">
                  <label>
                    طريقة الدفع
                    <select
                      value={paymentMethod}
                      onChange={(event) =>
                        setPaymentMethod(event.target.value as PaymentMethod)
                      }
                    >
                      <option value="cash">نقدي</option>
                      <option value="bank_transfer">تحويل بنكي</option>
                      <option value="cheque">شيك</option>
                      <option value="wallet">محفظة إلكترونية</option>
                    </select>
                  </label>
                  <label>
                    حساب الخزينة أو البنك
                    <select
                      value={financialAccountId}
                      onChange={(event) =>
                        setFinancialAccountId(event.target.value)
                      }
                      required
                    >
                      {compatibleAccounts.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name_ar} ·{" "}
                          {currency.format(Number(item.current_balance))}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <label>
                  المبلغ
                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                    required
                  />
                </label>
                <fieldset className="treasury-link-modes">
                  <legend>ربط الحركة</legend>
                  <label>
                    <input
                      type="radio"
                      checked={linkMode === "advance"}
                      onChange={() => setLinkMode("advance")}
                    />{" "}
                    دفعة غير مخصصة
                  </label>
                  <label>
                    <input
                      type="radio"
                      checked={linkMode === "order"}
                      onChange={() => setLinkMode("order")}
                    />{" "}
                    أمر بيع/شراء
                  </label>
                  <label>
                    <input
                      type="radio"
                      checked={linkMode === "invoices"}
                      onChange={() => setLinkMode("invoices")}
                    />{" "}
                    توزيع فواتير
                  </label>
                </fieldset>
                {linkMode === "order" ? (
                  <label>
                    المستند المفتوح
                    <select
                      value={orderId}
                      onChange={(event) => setOrderId(event.target.value)}
                      required
                    >
                      {openOrders.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.order_number} · متبقي{" "}
                          {currency.format(Number(item.remaining))}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {linkMode === "invoices" ? (
                  <div className="allocation-list">
                    {openInvoices.map((item) => (
                      <label key={item.id}>
                        <span>
                          <strong>{item.invoice_number}</strong>
                          <small>
                            متبقي {currency.format(Number(item.remaining))}
                          </small>
                        </span>
                        <input
                          type="number"
                          min="0"
                          max={item.remaining}
                          step="0.01"
                          value={allocationAmounts[item.id] || ""}
                          onChange={(event) =>
                            setAllocationAmounts((current) => ({
                              ...current,
                              [item.id]: event.target.value,
                            }))
                          }
                          placeholder="0.00"
                        />
                      </label>
                    ))}
                  </div>
                ) : null}
                <label>
                  ملاحظات
                  <input
                    value={paymentNotes}
                    onChange={(event) => setPaymentNotes(event.target.value)}
                  />
                </label>
                <button
                  className="primary-button"
                  disabled={submitting || !financialAccountId || !partnerId}
                >
                  <BadgeDollarSign size={17} /> اعتماد الحركة
                </button>
              </form>
            </article>
          ) : null}
        </section>
      ) : null}

      {tab === "accounts" ? (
        <>
          <section
            className={`master-layout treasury-layout ${canManage ? "" : "master-layout--single"}`}
          >
            <article className="panel">
              <header className="panel__head">
                <div>
                  <h3>الخزائن والبنوك والمحافظ</h3>
                  <p>الرصيد محسوب من دفتر الحركات لا من حقل قابل للتعديل</p>
                </div>
              </header>
              <div className="treasury-account-cards">
                {accounts.map((item) => (
                  <article
                    key={item.id}
                    className={`treasury-account-card ${item.is_active ? "" : "treasury-account-card--inactive"}`}
                  >
                    <span>
                      <Landmark size={20} />
                    </span>
                    <div>
                      <strong>{item.name_ar}</strong>
                      <small dir="ltr">
                        {item.code} · {item.account_type}
                      </small>
                    </div>
                    <b>{currency.format(Number(item.current_balance))} ج.م</b>
                    <div>
                      {item.is_default ? <em>افتراضي</em> : null}
                      {canManage ? (
                        <button
                          className="mini-action"
                          onClick={() => editAccount(item)}
                        >
                          تعديل
                        </button>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </article>
            {canManage ? (
              <article className="panel master-form-card">
                <header className="panel__head">
                  <div>
                    <h3>
                      {editingAccount ? "تعديل حساب مالي" : "حساب مالي جديد"}
                    </h3>
                    <p>الرصيد الافتتاحي يثبت عند الإنشاء فقط</p>
                  </div>
                </header>
                <form className="compact-form" onSubmit={saveAccount}>
                  <div className="form-pair">
                    <label>
                      الكود
                      <input
                        dir="ltr"
                        value={accountForm.code}
                        onChange={(e) =>
                          setAccountForm({
                            ...accountForm,
                            code: e.target.value,
                          })
                        }
                        required
                      />
                    </label>
                    <label>
                      الاسم
                      <input
                        value={accountForm.name_ar}
                        onChange={(e) =>
                          setAccountForm({
                            ...accountForm,
                            name_ar: e.target.value,
                          })
                        }
                        required
                      />
                    </label>
                  </div>
                  <div className="form-pair">
                    <label>
                      النوع
                      <select
                        value={accountForm.account_type}
                        onChange={(e) =>
                          setAccountForm({
                            ...accountForm,
                            account_type: e.target.value,
                          })
                        }
                      >
                        <option value="cash">خزينة نقدية</option>
                        <option value="bank">حساب بنكي</option>
                        <option value="wallet">محفظة</option>
                        <option value="other">آخر</option>
                      </select>
                    </label>
                    {!editingAccount ? (
                      <label>
                        الرصيد الافتتاحي
                        <input
                          type="number"
                          step="0.01"
                          value={accountForm.opening_balance}
                          onChange={(e) =>
                            setAccountForm({
                              ...accountForm,
                              opening_balance: e.target.value,
                            })
                          }
                        />
                      </label>
                    ) : null}
                  </div>
                  <label className="check-row">
                    <input
                      type="checkbox"
                      checked={accountForm.is_default}
                      onChange={(e) =>
                        setAccountForm({
                          ...accountForm,
                          is_default: e.target.checked,
                        })
                      }
                    />{" "}
                    الحساب الافتراضي
                  </label>
                  {editingAccount ? (
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={accountForm.is_active}
                        onChange={(e) =>
                          setAccountForm({
                            ...accountForm,
                            is_active: e.target.checked,
                          })
                        }
                      />{" "}
                      الحساب نشط
                    </label>
                  ) : null}
                  <label>
                    ملاحظات
                    <input
                      value={accountForm.notes}
                      onChange={(e) =>
                        setAccountForm({
                          ...accountForm,
                          notes: e.target.value,
                        })
                      }
                    />
                  </label>
                  <div className="form-actions">
                    <button className="primary-button">
                      <Check size={17} /> حفظ
                    </button>
                    {editingAccount ? (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => setEditingAccount(null)}
                      >
                        إلغاء
                      </button>
                    ) : null}
                  </div>
                </form>
              </article>
            ) : null}
          </section>
          {canManage ? (
            <section className="treasury-actions-grid">
              <article className="panel">
                <header className="panel__head">
                  <div>
                    <h3>تسوية رصيد مالي</h3>
                    <p>تسجيل الفرق للوصول إلى الرصيد الفعلي</p>
                  </div>
                  <Scale size={19} />
                </header>
                <form className="compact-form" onSubmit={postAdjustment}>
                  <label>
                    الحساب
                    <select
                      value={adjustmentForm.financial_account_id}
                      onChange={(e) =>
                        setAdjustmentForm({
                          ...adjustmentForm,
                          financial_account_id: e.target.value,
                        })
                      }
                    >
                      {accounts
                        .filter((x) => x.is_active)
                        .map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.name_ar}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    الرصيد الفعلي المستهدف
                    <input
                      type="number"
                      step="0.01"
                      value={adjustmentForm.target_balance}
                      onChange={(e) =>
                        setAdjustmentForm({
                          ...adjustmentForm,
                          target_balance: e.target.value,
                        })
                      }
                      required
                    />
                  </label>
                  <label>
                    سبب التسوية
                    <input
                      value={adjustmentForm.notes}
                      onChange={(e) =>
                        setAdjustmentForm({
                          ...adjustmentForm,
                          notes: e.target.value,
                        })
                      }
                      minLength={3}
                      required
                    />
                  </label>
                  <button className="primary-button">
                    <Scale size={17} /> تسجيل التسوية
                  </button>
                </form>
              </article>
            </section>
          ) : null}
        </>
      ) : null}

      {tab === "partners" ? (
        <>
          <section className="partner-balance-toolbar">
            <div className="sales-tabs">
              <button
                className={partnerType === "customer" ? "active" : ""}
                onClick={() => {
                  setPartnerType("customer");
                  setStatement(null);
                  setStatementPartnerId(
                    partners.find((x) => x.is_customer)?.id || "",
                  );
                }}
              >
                عملاء
              </button>
              <button
                className={partnerType === "supplier" ? "active" : ""}
                onClick={() => {
                  setPartnerType("supplier");
                  setStatement(null);
                  setStatementPartnerId(
                    partners.find((x) => x.is_supplier)?.id || "",
                  );
                }}
              >
                موردون
              </button>
            </div>
          </section>
          <section className="panel">
            <header className="panel__head">
              <div>
                <h3>
                  أرصدة {partnerType === "customer" ? "العملاء" : "الموردين"}
                </h3>
                <p>
                  صافي الفواتير بعد المرتجعات، والمدفوع بعد إظهار الاستردادات
                </p>
              </div>
            </header>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>الطرف</th>
                    <th>افتتاحي</th>
                    <th>صافي الفواتير</th>
                    <th>مرتجعات</th>
                    <th>مسدد</th>
                    <th>استردادات</th>
                    <th>مقدم</th>
                    <th>تسويات</th>
                    <th>الرصيد</th>
                  </tr>
                </thead>
                <tbody>
                  {balances.map((item) => (
                    <tr key={item.partner_id}>
                      <td>
                        <strong>{item.partner_name_ar}</strong>
                        <small dir="ltr">{item.partner_code}</small>
                      </td>
                      <td>{currency.format(Number(item.opening_balance))}</td>
                      <td>{currency.format(Number(item.invoices_total))}</td>
                      <td>{currency.format(Number(item.returns_total))}</td>
                      <td>{currency.format(Number(item.paid_total))}</td>
                      <td>{currency.format(Number(item.refunds_total))}</td>
                      <td>{currency.format(Number(item.advances))}</td>
                      <td>{currency.format(Number(item.adjustments_total))}</td>
                      <td>
                        <strong>{currency.format(Number(item.balance))}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="treasury-partner-grid">
            <article className="panel">
              <header className="panel__head">
                <div>
                  <h3>كشف حساب</h3>
                  <p>رصيد متحرك بين تاريخين</p>
                </div>
                <FileClock size={19} />
              </header>
              <form
                className="compact-form statement-form"
                onSubmit={loadStatement}
              >
                <label>
                  الطرف
                  <select
                    value={statementPartnerId}
                    onChange={(e) => setStatementPartnerId(e.target.value)}
                  >
                    {statementPartners.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.name_ar}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="form-pair">
                  <label>
                    من
                    <input
                      type="date"
                      value={statementFrom}
                      onChange={(e) => setStatementFrom(e.target.value)}
                    />
                  </label>
                  <label>
                    إلى
                    <input
                      type="date"
                      value={statementTo}
                      onChange={(e) => setStatementTo(e.target.value)}
                    />
                  </label>
                </div>
                <button className="primary-button">
                  <FileClock size={17} /> عرض الكشف
                </button>
              </form>
              {statement ? (
                <div className="statement-result">
                  <header>
                    <strong>{statement.partner_name_ar}</strong>
                    <span>
                      افتتاحي{" "}
                      {currency.format(Number(statement.opening_balance))} ·
                      ختامي {currency.format(Number(statement.closing_balance))}
                    </span>
                  </header>
                  <div className="data-table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>التاريخ</th>
                          <th>المستند</th>
                          <th>البيان</th>
                          <th>مدين</th>
                          <th>دائن</th>
                          <th>الرصيد</th>
                        </tr>
                      </thead>
                      <tbody>
                        {statement.lines.map((line, index) => (
                          <tr key={`${line.document_number}-${index}`}>
                            <td>
                              {new Date(line.movement_date).toLocaleDateString(
                                "ar-EG",
                              )}
                            </td>
                            <td dir="ltr">{line.document_number}</td>
                            <td>{line.movement_type}</td>
                            <td>{currency.format(Number(line.debit))}</td>
                            <td>{currency.format(Number(line.credit))}</td>
                            <td>
                              {currency.format(Number(line.running_balance))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </article>
            {canManage ? (
              <article className="treasury-side-actions">
                <section className="panel">
                  <header className="panel__head">
                    <div>
                      <h3>رصيد افتتاحي</h3>
                      <p>قيد ثابت يُصحح بالعكس فقط</p>
                    </div>
                  </header>
                  <form className="compact-form" onSubmit={postOpening}>
                    <label>
                      الطرف
                      <select
                        value={openingForm.partner_id}
                        onChange={(e) =>
                          setOpeningForm({
                            ...openingForm,
                            partner_id: e.target.value,
                          })
                        }
                      >
                        {partners.map((x) => (
                          <option key={x.id} value={x.id}>
                            {x.name_ar}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="form-pair">
                      <label>
                        الطبيعة
                        <select
                          value={openingForm.nature}
                          onChange={(e) =>
                            setOpeningForm({
                              ...openingForm,
                              nature: e.target.value,
                            })
                          }
                        >
                          <option value="debit">مدين</option>
                          <option value="credit">دائن</option>
                        </select>
                      </label>
                      <label>
                        المبلغ
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={openingForm.amount}
                          onChange={(e) =>
                            setOpeningForm({
                              ...openingForm,
                              amount: e.target.value,
                            })
                          }
                          required
                        />
                      </label>
                    </div>
                    <label>
                      التاريخ
                      <input
                        type="date"
                        value={openingForm.entry_date}
                        onChange={(e) =>
                          setOpeningForm({
                            ...openingForm,
                            entry_date: e.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      ملاحظات
                      <input
                        value={openingForm.notes}
                        onChange={(e) =>
                          setOpeningForm({
                            ...openingForm,
                            notes: e.target.value,
                          })
                        }
                      />
                    </label>
                    <button className="primary-button">تسجيل الرصيد</button>
                  </form>
                  <div className="compact-history">
                    {openingBalances.slice(0, 6).map((item) => (
                      <div key={item.id}>
                        <span>
                          <strong>{item.partner_name_ar}</strong>
                          <small>
                            {item.entry_number} ·{" "}
                            {item.nature === "debit" ? "مدين" : "دائن"}
                          </small>
                        </span>
                        <b>{currency.format(Number(item.amount))}</b>
                        {item.status === "posted" ? (
                          <button
                            className="mini-action"
                            onClick={() =>
                              void reverse(
                                "/accounts/opening-balances",
                                item.id,
                                "الرصيد الافتتاحي",
                                false,
                              )
                            }
                          >
                            <RotateCcw size={13} />
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </section>
                <section className="panel">
                  <header className="panel__head">
                    <div>
                      <h3>تسوية حساب عميل</h3>
                      <p>خصم مسموح أو إضافة مدينة</p>
                    </div>
                  </header>
                  <form
                    className="compact-form"
                    onSubmit={postCustomerAdjustment}
                  >
                    <label>
                      العميل
                      <select
                        value={customerAdjustmentForm.customer_id}
                        onChange={(e) =>
                          setCustomerAdjustmentForm({
                            ...customerAdjustmentForm,
                            customer_id: e.target.value,
                          })
                        }
                      >
                        {partners
                          .filter((x) => x.is_customer)
                          .map((x) => (
                            <option key={x.id} value={x.id}>
                              {x.name_ar}
                            </option>
                          ))}
                      </select>
                    </label>
                    <div className="form-pair">
                      <label>
                        النوع
                        <select
                          value={customerAdjustmentForm.adjustment_type}
                          onChange={(e) =>
                            setCustomerAdjustmentForm({
                              ...customerAdjustmentForm,
                              adjustment_type: e.target.value,
                            })
                          }
                        >
                          <option value="debit">مدينة</option>
                          <option value="credit">دائنة</option>
                        </select>
                      </label>
                      <label>
                        المبلغ
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={customerAdjustmentForm.amount}
                          onChange={(e) =>
                            setCustomerAdjustmentForm({
                              ...customerAdjustmentForm,
                              amount: e.target.value,
                            })
                          }
                          required
                        />
                      </label>
                    </div>
                    <label>
                      السبب
                      <input
                        value={customerAdjustmentForm.notes}
                        onChange={(e) =>
                          setCustomerAdjustmentForm({
                            ...customerAdjustmentForm,
                            notes: e.target.value,
                          })
                        }
                        minLength={3}
                        required
                      />
                    </label>
                    <button className="primary-button">تسجيل التسوية</button>
                  </form>
                  <div className="compact-history">
                    {customerAdjustments.slice(0, 6).map((item) => (
                      <div key={item.id}>
                        <span>
                          <strong>{item.customer_name_ar}</strong>
                          <small>
                            {item.adjustment_number} · {item.notes}
                          </small>
                        </span>
                        <b>{currency.format(Number(item.amount))}</b>
                        {item.status === "posted" ? (
                          <button
                            className="mini-action"
                            onClick={() =>
                              void reverse(
                                "/accounts/customer-adjustments",
                                item.id,
                                "تسوية العميل",
                                false,
                              )
                            }
                          >
                            <RotateCcw size={13} />
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </section>
              </article>
            ) : null}
          </section>
        </>
      ) : null}
      {tab === "sales-invoices" || tab === "purchase-invoices" ? (
        <section className="panel accounts-invoices-panel">
          <header className="panel__head">
            <div>
              <h3>{tab === "sales-invoices" ? "فواتير المبيعات" : "فواتير المشتريات"}</h3>
              <p>الإجمالي والمرتجع والصافي والمدفوع والمتبقي</p>
            </div>
            <span className="status-badge status-badge--active">{displayedInvoices.length}</span>
          </header>
          <input className="accounts-invoice-search" value={invoiceSearch} onChange={(event) => setInvoiceSearch(event.target.value)} placeholder="بحث برقم الفاتورة أو الأمر أو الاسم أو الهاتف أو طريقة الدفع" />
          <div className="data-table-wrap">
            <table className="data-table treasury-invoices-table">
              <thead><tr><th>رقم الفاتورة</th><th>رقم الأمر</th><th>الوقت</th><th>{tab === "sales-invoices" ? "العميل" : "المورد"}</th><th>الهاتف</th><th>الإجمالي الأصلي</th><th>المرتجع</th><th>صافي الفاتورة</th><th>المدفوع</th><th>طريقة الدفع</th><th>المتبقي</th><th>حالة الفاتورة</th><th>حالة التسليم / المرتجع</th><th>حالة الدفع</th><th/></tr></thead>
              <tbody>{displayedInvoices.map((item) => <tr key={item.id}>
                <td dir="ltr"><strong>{item.invoice_number}</strong></td>
                <td dir="ltr">{item.order_number}</td>
                <td>{new Date(item.invoice_date).toLocaleString("ar-EG")}</td>
                <td>{item.partner_name_ar}</td>
                <td dir="ltr">{item.partner_phone || "—"}</td>
                <td>{currency.format(Number(item.original_total))}</td>
                <td>{currency.format(Number(item.returned_total))}</td>
                <td><strong>{currency.format(Number(item.net_total))}</strong></td>
                <td>{currency.format(Math.max(0, Number(item.paid) - Number(item.refunded)))}</td>
                <td>{(item.payment_methods ?? []).length ? (item.payment_methods ?? []).map((method) => methodLabels[method]).join("، ") : "—"}</td>
                <td>{currency.format(Number(item.remaining))}</td>
                <td><span className="purchase-status purchase-status--received">{item.invoice_status === "posted" ? "معتمدة" : item.invoice_status}</span></td>
                <td><span className={`purchase-status purchase-status--${item.return_status === "none" ? "received" : item.return_status === "partial" ? "approved" : "cancelled"}`}>{item.delivery_return_status}</span></td>
                <td><span className={`purchase-status purchase-status--${item.payment_status === "paid" ? "received" : item.payment_status === "partial" ? "approved" : "cancelled"}`}>{item.payment_status === "paid" ? "مدفوعة" : item.payment_status === "partial" ? "مدفوعة جزئيًا" : "غير مدفوعة"}</span></td>
                <td><span className="invoice-row-actions">{canManage && Number(item.remaining) > 0 ? <button className="mini-action" onClick={() => payInvoice(item)}>{item.invoice_type === "sales" ? "تحصيل" : "سداد"}</button> : null}{canReturns && item.return_status !== "full" ? <button className="mini-action" onClick={() => returnInvoice(item)}>إنشاء مرتجع</button> : null}</span></td>
              </tr>)}</tbody>
            </table>
          </div>
          {!displayedInvoices.length ? <div className="empty-state"><h4>لا توجد فواتير معتمدة</h4></div> : null}
        </section>
      ) : null}

      {tab === "returns" && canReturns ? <ReturnsWorkspace embedded initialType={returnTarget?.invoice_type} initialInvoiceId={returnTarget?.id} /> : null}
    </AppShell>
  );
}
