import { Check, RefreshCw, UserRoundPlus, UsersRound } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [isCustomer, setIsCustomer] = useState(true);
  const [isSupplier, setIsSupplier] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPartners(await api<Partner[]>("/master-data/partners"));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل العملاء والموردين");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createPartner(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api<Partner>("/master-data/partners", {
        method: "POST",
        body: JSON.stringify({
          code,
          name_ar: name,
          phone,
          address,
          tax_number: "",
          is_customer: isCustomer,
          is_supplier: isSupplier,
        }),
      });
      setCode("");
      setName("");
      setPhone("");
      setAddress("");
      setNotice("تم إنشاء السجل ويمكن استخدامه في العمليات المسموح بها.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء السجل");
    }
  }

  return (
    <AppShell>
      <section className="page-heading">
        <div><span className="eyebrow">البيانات الأساسية</span><h2>العملاء والموردون</h2><p>سجل موحد يسمح للجهة نفسها أن تكون عميلًا وموردًا دون تكرار.</p></div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17} /> تحديث</button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      <section className={`master-layout ${canManage ? "" : "master-layout--single"}`}>
        <article className="panel"><header className="panel__head"><div><h3>دليل الشركاء</h3><p>{partners.length} سجلًا نشطًا</p></div></header>{partners.length ? <div className="partner-cards">{partners.map((partner) => <article className="partner-card" key={partner.id}><span className="partner-card__avatar">{partner.name_ar.charAt(0)}</span><div><strong>{partner.name_ar}</strong><small dir="ltr">{partner.code} · {partner.phone || "بدون هاتف"}</small><div className="permission-chips">{partner.is_customer ? <span>عميل</span> : null}{partner.is_supplier ? <span>مورد</span> : null}</div></div></article>)}</div> : <div className="empty-state"><span className="empty-state__icon"><UsersRound size={27} /></span><h4>لا توجد جهات بعد</h4><p>أنشئ أول عميل أو مورد لاستخدامه في المستندات.</p></div>}</article>

        {canManage ? <article className="panel master-form-card"><header className="panel__head"><div><h3>جهة جديدة</h3><p>يمكن اختيار عميل ومورد معًا</p></div></header><form className="compact-form" onSubmit={createPartner}><label>الكود<input dir="ltr" value={code} onChange={(event) => setCode(event.target.value)} placeholder="C-001" required /></label><label>الاسم<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} /></label><label>الهاتف<input dir="ltr" value={phone} onChange={(event) => setPhone(event.target.value)} /></label><label>العنوان<input value={address} onChange={(event) => setAddress(event.target.value)} /></label><fieldset className="partner-types"><legend>نوع الجهة</legend><label className="check-field"><input type="checkbox" checked={isCustomer} onChange={(event) => setIsCustomer(event.target.checked)} /> عميل</label><label className="check-field"><input type="checkbox" checked={isSupplier} onChange={(event) => setIsSupplier(event.target.checked)} /> مورد</label></fieldset><button className="primary-button" disabled={!isCustomer && !isSupplier}><UserRoundPlus size={17} /> حفظ الجهة</button></form></article> : null}
      </section>
    </AppShell>
  );
}
