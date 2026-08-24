import {
  Check,
  Pencil,
  RefreshCw,
  UserRoundPlus,
  UsersRound,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Partner = {
  id: string;
  code: string;
  name_ar: string;
  phone: string;
  address: string;
  tax_number: string;
  is_customer: boolean;
  is_supplier: boolean;
  is_active: boolean;
  version: number;
};

export function PartnersPage() {
  const { user } = useAuth();
  const location = useLocation();
  const partnerType =
    new URLSearchParams(location.search).get("type") === "supplier"
      ? "supplier"
      : "customer";
  const title = partnerType === "supplier" ? "الموردين" : "العملاء";
  const singular = partnerType === "supplier" ? "مورد" : "عميل";
  const canManage = user?.permissions.includes("partners.manage") ?? false;
  const [partners, setPartners] = useState<Partner[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [taxNumber, setTaxNumber] = useState("");
  const [isCustomer, setIsCustomer] = useState(partnerType === "customer");
  const [isSupplier, setIsSupplier] = useState(partnerType === "supplier");
  const [isActive, setIsActive] = useState(true);
  const [editing, setEditing] = useState<Partner | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPartners(
        await api<Partner[]>(
          `/master-data/partners${canManage ? "?include_inactive=true" : ""}`,
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : "تعذر تحميل العملاء والموردين",
      );
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setEditing(null);
    setCode("");
    setName("");
    setPhone("");
    setAddress("");
    setTaxNumber("");
    setIsCustomer(partnerType === "customer");
    setIsSupplier(partnerType === "supplier");
    setIsActive(true);
  }, [partnerType]);

  async function savePartner(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api<Partner>(
        editing
          ? `/master-data/partners/${editing.id}`
          : "/master-data/partners",
        {
          method: editing ? "PUT" : "POST",
          body: JSON.stringify({
            ...(editing
              ? { version: editing.version, is_active: isActive }
              : {}),
            code,
            name_ar: name,
            phone,
            address,
            tax_number: taxNumber,
            is_customer: isCustomer,
            is_supplier: isSupplier,
          }),
        },
      );
      resetForm();
      setNotice(
        editing ? `تم تحديث بيانات ${singular}.` : `تم إنشاء ${singular} جديد.`,
      );
      await load();
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "تعذر إنشاء السجل",
      );
    }
  }

  function resetForm() {
    setEditing(null);
    setCode("");
    setName("");
    setPhone("");
    setAddress("");
    setTaxNumber("");
    setIsCustomer(partnerType === "customer");
    setIsSupplier(partnerType === "supplier");
    setIsActive(true);
  }

  function editPartner(item: Partner) {
    setEditing(item);
    setCode(item.code);
    setName(item.name_ar);
    setPhone(item.phone);
    setAddress(item.address);
    setTaxNumber(item.tax_number);
    setIsCustomer(item.is_customer);
    setIsSupplier(item.is_supplier);
    setIsActive(item.is_active);
  }

  const visiblePartners = useMemo(() => {
    const token = search.trim().toLocaleLowerCase("ar");
    const matchingType = partners.filter((item) =>
      partnerType === "supplier" ? item.is_supplier : item.is_customer,
    );
    if (!token) return matchingType;
    return matchingType.filter((item) =>
      [item.code, item.name_ar, item.phone, item.address, item.tax_number]
        .join(" ")
        .toLocaleLowerCase("ar")
        .includes(token),
    );
  }, [partnerType, partners, search]);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <h2>{title}</h2>
          <p>إضافة وتعديل بيانات {title} المستخدمة في العمليات والحسابات.</p>
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

      <section
        className={`master-layout ${canManage ? "" : "master-layout--single"}`}
      >
        <article className="panel">
          <header className="panel__head">
            <div>
              <h3>{title}</h3>
              <p>
                {visiblePartners.filter((item) => item.is_active).length} سجلًا
                نشطًا
              </p>
            </div>
          </header>
          <div className="partner-search">
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="بحث بالاسم أو الكود أو الهاتف أو العنوان"
              aria-label={`بحث في ${title}`}
            />
          </div>
          {visiblePartners.length ? (
            <div className="partner-cards">
              {visiblePartners.map((partner) => (
                <article
                  className={`partner-card ${partner.is_active ? "" : "partner-card--inactive"}`}
                  key={partner.id}
                >
                  <span className="partner-card__avatar">
                    {partner.name_ar.charAt(0)}
                  </span>
                  <div>
                    <strong>{partner.name_ar}</strong>
                    <small dir="ltr">
                      {partner.code} · {partner.phone || "بدون هاتف"}
                    </small>
                    {!partner.is_active ? (
                      <div className="permission-chips">
                        <span>متوقف</span>
                      </div>
                    ) : null}
                  </div>
                  {canManage ? (
                    <button
                      className="mini-action partner-card__edit"
                      onClick={() => editPartner(partner)}
                      aria-label={`تعديل ${singular}`}
                    >
                      <Pencil size={15} />
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-state__icon">
                <UsersRound size={27} />
              </span>
              <h4>
                {partners.length
                  ? "لا توجد نتائج مطابقة"
                  : `لا يوجد ${title} بعد`}
              </h4>
              <p>
                {partners.length
                  ? "جرّب اسمًا أو كودًا أو رقم هاتف آخر."
                  : `أنشئ أول ${singular} لاستخدامه في المستندات.`}
              </p>
            </div>
          )}
        </article>

        {canManage ? (
          <article className="panel master-form-card">
            <header className="panel__head">
              <div>
                <h3>{editing ? `تعديل ${singular}` : `${singular} جديد`}</h3>
              </div>
            </header>
            <form className="compact-form" onSubmit={savePartner}>
              <label>
                الكود
                <input
                  dir="ltr"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder={partnerType === "supplier" ? "S-001" : "C-001"}
                  required
                />
              </label>
              <label>
                الاسم
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  minLength={2}
                />
              </label>
              <label>
                الهاتف
                <input
                  dir="ltr"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                />
              </label>
              <label>
                العنوان
                <input
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                />
              </label>
              <label>
                الرقم الضريبي
                <input
                  dir="ltr"
                  value={taxNumber}
                  onChange={(event) => setTaxNumber(event.target.value)}
                />
              </label>
              {editing ? (
                <label className="check-field">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={(event) => setIsActive(event.target.checked)}
                  />{" "}
                  {singular} نشط
                </label>
              ) : null}
              <div className="form-actions">
                <button className="primary-button">
                  <UserRoundPlus size={17} />{" "}
                  {editing ? "حفظ التعديل" : `حفظ ${singular}`}
                </button>
                {editing ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={resetForm}
                  >
                    <X size={16} /> إلغاء
                  </button>
                ) : null}
              </div>
            </form>
          </article>
        ) : null}
      </section>
    </AppShell>
  );
}
