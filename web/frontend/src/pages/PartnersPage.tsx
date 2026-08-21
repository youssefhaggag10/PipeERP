import { Check, Pencil, RefreshCw, UserRoundPlus, UsersRound, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

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
  const [isCustomer, setIsCustomer] = useState(true);
  const [isSupplier, setIsSupplier] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [editing, setEditing] = useState<Partner | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPartners(await api<Partner[]>(`/master-data/partners${canManage ? "?include_inactive=true" : ""}`));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل العملاء والموردين");
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    void load();
  }, [load]);

  async function savePartner(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api<Partner>(editing ? `/master-data/partners/${editing.id}` : "/master-data/partners", {
        method: editing ? "PUT" : "POST",
        body: JSON.stringify({
          ...(editing ? { version: editing.version, is_active: isActive } : {}),
          code,
          name_ar: name,
          phone,
          address,
          tax_number: taxNumber,
          is_customer: isCustomer,
          is_supplier: isSupplier,
        }),
      });
      resetForm();
      setNotice(editing ? "تم تحديث بيانات الجهة." : "تم إنشاء السجل ويمكن استخدامه في العمليات المسموح بها.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء السجل");
    }
  }

  function resetForm() {
    setEditing(null);
    setCode("");
    setName("");
    setPhone("");
    setAddress("");
    setTaxNumber("");
    setIsCustomer(true);
    setIsSupplier(false);
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
    if (!token) return partners;
    return partners.filter((item) =>
      [item.code, item.name_ar, item.phone, item.address, item.tax_number]
        .join(" ")
        .toLocaleLowerCase("ar")
        .includes(token),
    );
  }, [partners, search]);

  return (
    <AppShell>
      <section className="page-heading">
        <div><span className="eyebrow">البيانات الأساسية</span><h2>العملاء والموردون</h2><p>سجل موحد يسمح للجهة نفسها أن تكون عميلًا وموردًا دون تكرار.</p></div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17} /> تحديث</button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      <section className={`master-layout ${canManage ? "" : "master-layout--single"}`}>
        <article className="panel"><header className="panel__head"><div><h3>دليل الشركاء</h3><p>{partners.filter((item) => item.is_active).length} سجلًا نشطًا</p></div></header><div className="partner-search"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="بحث بالاسم أو الكود أو الهاتف أو العنوان" aria-label="بحث في العملاء والموردين" /></div>{visiblePartners.length ? <div className="partner-cards">{visiblePartners.map((partner) => <article className={`partner-card ${partner.is_active ? "" : "partner-card--inactive"}`} key={partner.id}><span className="partner-card__avatar">{partner.name_ar.charAt(0)}</span><div><strong>{partner.name_ar}</strong><small dir="ltr">{partner.code} · {partner.phone || "بدون هاتف"}</small><div className="permission-chips">{partner.is_customer ? <span>عميل</span> : null}{partner.is_supplier ? <span>مورد</span> : null}{!partner.is_active ? <span>متوقف</span> : null}</div></div>{canManage ? <button className="mini-action partner-card__edit" onClick={() => editPartner(partner)} aria-label="تعديل الجهة"><Pencil size={15} /></button> : null}</article>)}</div> : <div className="empty-state"><span className="empty-state__icon"><UsersRound size={27} /></span><h4>{partners.length ? "لا توجد نتائج مطابقة" : "لا توجد جهات بعد"}</h4><p>{partners.length ? "جرّب اسمًا أو كودًا أو رقم هاتف آخر." : "أنشئ أول عميل أو مورد لاستخدامه في المستندات."}</p></div>}</article>

        {canManage ? <article className="panel master-form-card"><header className="panel__head"><div><h3>{editing ? "تعديل الجهة" : "جهة جديدة"}</h3><p>يمكن اختيار عميل ومورد معًا</p></div></header><form className="compact-form" onSubmit={savePartner}><label>الكود<input dir="ltr" value={code} onChange={(event) => setCode(event.target.value)} placeholder="C-001" required /></label><label>الاسم<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} /></label><label>الهاتف<input dir="ltr" value={phone} onChange={(event) => setPhone(event.target.value)} /></label><label>العنوان<input value={address} onChange={(event) => setAddress(event.target.value)} /></label><label>الرقم الضريبي<input dir="ltr" value={taxNumber} onChange={(event) => setTaxNumber(event.target.value)} /></label><fieldset className="partner-types"><legend>نوع الجهة</legend><label className="check-field"><input type="checkbox" checked={isCustomer} onChange={(event) => setIsCustomer(event.target.checked)} /> عميل</label><label className="check-field"><input type="checkbox" checked={isSupplier} onChange={(event) => setIsSupplier(event.target.checked)} /> مورد</label></fieldset>{editing ? <label className="check-field"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /> الجهة نشطة</label> : null}<div className="form-actions"><button className="primary-button" disabled={!isCustomer && !isSupplier}><UserRoundPlus size={17} /> {editing ? "حفظ التعديل" : "حفظ الجهة"}</button>{editing ? <button type="button" className="secondary-button" onClick={resetForm}><X size={16} /> إلغاء</button> : null}</div></form></article> : null}
      </section>
    </AppShell>
  );
}
