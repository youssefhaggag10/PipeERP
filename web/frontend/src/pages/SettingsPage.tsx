import {
  Building2,
  Check,
  Layers3,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Ruler,
  Save,
  Star,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Unit = {
  id: string;
  code: string;
  name_ar: string;
  symbol: string;
  decimal_places: number;
  is_active: boolean;
  version: number;
};

type Category = {
  id: string;
  code: string;
  name_ar: string;
  parent_id: string | null;
  is_active: boolean;
  version: number;
};

type Warehouse = {
  id: string;
  code: string;
  name_ar: string;
  is_default: boolean;
  is_active: boolean;
  version: number;
};

type CompanySettings = {
  company_name_ar: string;
  phone: string;
  address: string;
  tax_number: string;
  currency_code: string;
  currency_decimal_places: number;
  tax_enabled: boolean;
  default_tax_rate: string;
  default_warehouse_id: string | null;
  version: number;
};

const emptyUnit = { code: "", name: "", symbol: "", decimalPlaces: 3 };
const emptyCategory = { code: "", name: "", parentId: "" };
const emptyWarehouse = { code: "", name: "", isDefault: false };

export function SettingsPage() {
  const { user } = useAuth();
  const canReadProducts = user?.permissions.includes("products.read") ?? false;
  const canManageProducts = user?.permissions.includes("products.manage") ?? false;
  const canReadWarehouses = user?.permissions.includes("warehouses.read") ?? false;
  const canManageWarehouses = user?.permissions.includes("warehouses.manage") ?? false;
  const canManageSettings = user?.permissions.includes("settings.manage") ?? false;
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [unitForm, setUnitForm] = useState(emptyUnit);
  const [categoryForm, setCategoryForm] = useState(emptyCategory);
  const [warehouseForm, setWarehouseForm] = useState(emptyWarehouse);
  const [editingUnit, setEditingUnit] = useState<Unit | null>(null);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [editingWarehouse, setEditingWarehouse] = useState<Warehouse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [company, warehouseRows, unitRows, categoryRows] = await Promise.all([
        api<CompanySettings>("/master-data/settings"),
        canReadWarehouses
          ? api<Warehouse[]>(`/master-data/warehouses${canManageWarehouses ? "?include_inactive=true" : ""}`)
          : Promise.resolve([]),
        canReadProducts
          ? api<Unit[]>(`/master-data/units${canManageProducts ? "?include_inactive=true" : ""}`)
          : Promise.resolve([]),
        canReadProducts
          ? api<Category[]>(`/master-data/categories${canManageProducts ? "?include_inactive=true" : ""}`)
          : Promise.resolve([]),
      ]);
      setSettings(company);
      setWarehouses(warehouseRows);
      setUnits(unitRows);
      setCategories(categoryRows);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل الإعدادات");
    } finally {
      setLoading(false);
    }
  }, [canManageProducts, canManageWarehouses, canReadProducts, canReadWarehouses]);

  useEffect(() => {
    void load();
  }, [load]);

  function reportError(reason: unknown, fallback: string) {
    setError(reason instanceof ApiError ? reason.message : fallback);
  }

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setError("");
    try {
      const updated = await api<CompanySettings>("/master-data/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setSettings(updated);
      setNotice("تم حفظ إعدادات الشركة وتسجيل التغيير في سجل التدقيق.");
    } catch (reason) {
      reportError(reason, "تعذر حفظ إعدادات الشركة");
    }
  }

  async function saveUnit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const payload = {
        code: unitForm.code,
        name_ar: unitForm.name,
        symbol: unitForm.symbol,
        decimal_places: unitForm.decimalPlaces,
        ...(editingUnit ? { version: editingUnit.version, is_active: editingUnit.is_active } : {}),
      };
      await api<Unit>(editingUnit ? `/master-data/units/${editingUnit.id}` : "/master-data/units", {
        method: editingUnit ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      setUnitForm(emptyUnit);
      setEditingUnit(null);
      setNotice(editingUnit ? "تم تحديث وحدة القياس." : "تمت إضافة وحدة القياس.");
      await load();
    } catch (reason) {
      reportError(reason, "تعذر حفظ وحدة القياس");
    }
  }

  async function saveCategory(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const payload = {
        code: categoryForm.code,
        name_ar: categoryForm.name,
        parent_id: categoryForm.parentId || null,
        ...(editingCategory
          ? { version: editingCategory.version, is_active: editingCategory.is_active }
          : {}),
      };
      await api<Category>(
        editingCategory ? `/master-data/categories/${editingCategory.id}` : "/master-data/categories",
        { method: editingCategory ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      setCategoryForm(emptyCategory);
      setEditingCategory(null);
      setNotice(editingCategory ? "تم تحديث التصنيف." : "تمت إضافة التصنيف.");
      await load();
    } catch (reason) {
      reportError(reason, "تعذر حفظ التصنيف");
    }
  }

  async function saveWarehouse(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const payload = {
        code: warehouseForm.code,
        name_ar: warehouseForm.name,
        is_default: warehouseForm.isDefault,
        ...(editingWarehouse
          ? { version: editingWarehouse.version, is_active: editingWarehouse.is_active }
          : {}),
      };
      await api<Warehouse>(
        editingWarehouse
          ? `/master-data/warehouses/${editingWarehouse.id}`
          : "/master-data/warehouses",
        { method: editingWarehouse ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      setWarehouseForm(emptyWarehouse);
      setEditingWarehouse(null);
      setNotice(editingWarehouse ? "تم تحديث المخزن." : "تمت إضافة المخزن.");
      await load();
    } catch (reason) {
      reportError(reason, "تعذر حفظ المخزن");
    }
  }

  async function toggleUnit(item: Unit) {
    try {
      await api<Unit>(`/master-data/units/${item.id}`, {
        method: "PUT",
        body: JSON.stringify({
          version: item.version,
          code: item.code,
          name_ar: item.name_ar,
          symbol: item.symbol,
          decimal_places: item.decimal_places,
          is_active: !item.is_active,
        }),
      });
      await load();
    } catch (reason) {
      reportError(reason, "تعذر تغيير حالة الوحدة");
    }
  }

  async function toggleCategory(item: Category) {
    try {
      await api<Category>(`/master-data/categories/${item.id}`, {
        method: "PUT",
        body: JSON.stringify({
          version: item.version,
          code: item.code,
          name_ar: item.name_ar,
          parent_id: item.parent_id,
          is_active: !item.is_active,
        }),
      });
      await load();
    } catch (reason) {
      reportError(reason, "تعذر تغيير حالة التصنيف");
    }
  }

  async function updateWarehouseState(item: Warehouse, changes: Partial<Warehouse>) {
    try {
      await api<Warehouse>(`/master-data/warehouses/${item.id}`, {
        method: "PUT",
        body: JSON.stringify({
          version: item.version,
          code: item.code,
          name_ar: item.name_ar,
          is_default: item.is_default,
          is_active: item.is_active,
          ...changes,
        }),
      });
      await load();
    } catch (reason) {
      reportError(reason, "تعذر تغيير حالة المخزن");
    }
  }

  function editUnit(item: Unit) {
    setEditingUnit(item);
    setUnitForm({
      code: item.code,
      name: item.name_ar,
      symbol: item.symbol,
      decimalPlaces: item.decimal_places,
    });
  }

  function editCategory(item: Category) {
    setEditingCategory(item);
    setCategoryForm({ code: item.code, name: item.name_ar, parentId: item.parent_id ?? "" });
  }

  function editWarehouse(item: Warehouse) {
    setEditingWarehouse(item);
    setWarehouseForm({ code: item.code, name: item.name_ar, isDefault: item.is_default });
  }

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <span className="eyebrow">تهيئة المنصة</span>
          <h2>الإعدادات والبيانات المرجعية</h2>
          <p>هوية الشركة ووحدات القياس والتصنيفات والمخازن في مساحة إدارة واحدة وآمنة.</p>
        </div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={17} /> تحديث
        </button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      {settings ? (
        <section className="settings-layout">
          <article className="panel settings-company">
            <header className="panel__head">
              <div><h3>بيانات الشركة</h3><p>تُستخدم لاحقًا في مستندات وتقارير A4</p></div>
              <Building2 size={20} />
            </header>
            <form className="settings-form" onSubmit={saveSettings}>
              <label>اسم الشركة<input value={settings.company_name_ar} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, company_name_ar: event.target.value })} required /></label>
              <label>الهاتف<input dir="ltr" value={settings.phone} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, phone: event.target.value })} /></label>
              <label className="settings-form__wide">العنوان<input value={settings.address} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, address: event.target.value })} /></label>
              <label>الرقم الضريبي<input dir="ltr" value={settings.tax_number} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, tax_number: event.target.value })} /></label>
              <label>العملة<input dir="ltr" maxLength={3} value={settings.currency_code} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, currency_code: event.target.value.toUpperCase() })} required /></label>
              <label>المنازل العشرية<input type="number" min="0" max="4" value={settings.currency_decimal_places} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, currency_decimal_places: Number(event.target.value) })} /></label>
              <label>نسبة الضريبة الافتراضية<input type="number" min="0" max="100" step="0.001" value={settings.default_tax_rate} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, default_tax_rate: event.target.value })} /></label>
              <label className="check-field settings-form__check"><input type="checkbox" checked={settings.tax_enabled} disabled={!canManageSettings} onChange={(event) => setSettings({ ...settings, tax_enabled: event.target.checked })} /> تفعيل الضرائب</label>
              {canManageSettings ? <button className="primary-button settings-form__submit"><Save size={17} /> حفظ بيانات الشركة</button> : null}
            </form>
          </article>

          {canReadWarehouses ? (
            <ReferenceSection
              icon={<MapPin size={20} />}
              title="المخازن"
              subtitle="مخزن افتراضي واحد فقط للنظام"
              form={canManageWarehouses ? (
                <form className="reference-form" onSubmit={saveWarehouse}>
                  <input dir="ltr" placeholder="الكود" value={warehouseForm.code} onChange={(event) => setWarehouseForm({ ...warehouseForm, code: event.target.value })} required />
                  <input placeholder="اسم المخزن" value={warehouseForm.name} onChange={(event) => setWarehouseForm({ ...warehouseForm, name: event.target.value })} required />
                  <label className="check-field"><input type="checkbox" checked={warehouseForm.isDefault} onChange={(event) => setWarehouseForm({ ...warehouseForm, isDefault: event.target.checked })} /> افتراضي</label>
                  <button className="primary-button primary-button--compact"><Plus size={16} /> {editingWarehouse ? "حفظ التعديل" : "إضافة"}</button>
                </form>
              ) : null}
            >
              {warehouses.map((item) => (
                <ReferenceRow key={item.id} code={item.code} name={item.name_ar} active={item.is_active} badge={item.is_default ? "افتراضي" : undefined}>
                  {canManageWarehouses ? <>
                    <button className="mini-action" onClick={() => editWarehouse(item)} aria-label="تعديل المخزن"><Pencil size={15} /></button>
                    {!item.is_default ? <button className="mini-action" onClick={() => void updateWarehouseState(item, { is_default: true })} aria-label="تعيين كمخزن افتراضي"><Star size={15} /></button> : null}
                    <button className="mini-action" disabled={item.is_default} onClick={() => void updateWarehouseState(item, { is_active: !item.is_active })} aria-label="تغيير حالة المخزن">{item.is_active ? <ToggleRight size={17} /> : <ToggleLeft size={17} />}</button>
                  </> : null}
                </ReferenceRow>
              ))}
            </ReferenceSection>
          ) : null}

          {canReadProducts ? <>
            <ReferenceSection
              icon={<Ruler size={20} />}
              title="وحدات القياس"
              subtitle="دقة الكميات والرمز الظاهر في المستندات"
              form={canManageProducts ? (
                <form className="reference-form reference-form--four" onSubmit={saveUnit}>
                  <input dir="ltr" placeholder="الكود" value={unitForm.code} onChange={(event) => setUnitForm({ ...unitForm, code: event.target.value })} required />
                  <input placeholder="الاسم" value={unitForm.name} onChange={(event) => setUnitForm({ ...unitForm, name: event.target.value })} required />
                  <input placeholder="الرمز" value={unitForm.symbol} onChange={(event) => setUnitForm({ ...unitForm, symbol: event.target.value })} required />
                  <input type="number" aria-label="المنازل العشرية" min="0" max="6" value={unitForm.decimalPlaces} onChange={(event) => setUnitForm({ ...unitForm, decimalPlaces: Number(event.target.value) })} />
                  <button className="primary-button primary-button--compact"><Plus size={16} /> {editingUnit ? "حفظ التعديل" : "إضافة"}</button>
                </form>
              ) : null}
            >
              {units.map((item) => (
                <ReferenceRow key={item.id} code={item.code} name={`${item.name_ar} · ${item.symbol}`} active={item.is_active} badge={`${item.decimal_places} عشري`}>
                  {canManageProducts ? <><button className="mini-action" onClick={() => editUnit(item)} aria-label="تعديل الوحدة"><Pencil size={15} /></button><button className="mini-action" onClick={() => void toggleUnit(item)} aria-label="تغيير حالة الوحدة">{item.is_active ? <ToggleRight size={17} /> : <ToggleLeft size={17} />}</button></> : null}
                </ReferenceRow>
              ))}
            </ReferenceSection>

            <ReferenceSection
              icon={<Layers3 size={20} />}
              title="تصنيفات المنتجات"
              subtitle="هيكل مرن للتجميع والتقارير"
              form={canManageProducts ? (
                <form className="reference-form" onSubmit={saveCategory}>
                  <input dir="ltr" placeholder="الكود" value={categoryForm.code} onChange={(event) => setCategoryForm({ ...categoryForm, code: event.target.value })} required />
                  <input placeholder="اسم التصنيف" value={categoryForm.name} onChange={(event) => setCategoryForm({ ...categoryForm, name: event.target.value })} required />
                  <select aria-label="التصنيف الأب" value={categoryForm.parentId} onChange={(event) => setCategoryForm({ ...categoryForm, parentId: event.target.value })}><option value="">بدون تصنيف أب</option>{categories.filter((item) => item.id !== editingCategory?.id && item.is_active).map((item) => <option key={item.id} value={item.id}>{item.name_ar}</option>)}</select>
                  <button className="primary-button primary-button--compact"><Plus size={16} /> {editingCategory ? "حفظ التعديل" : "إضافة"}</button>
                </form>
              ) : null}
            >
              {categories.map((item) => (
                <ReferenceRow key={item.id} code={item.code} name={item.name_ar} active={item.is_active} badge={item.parent_id ? "فرعي" : "رئيسي"}>
                  {canManageProducts ? <><button className="mini-action" onClick={() => editCategory(item)} aria-label="تعديل التصنيف"><Pencil size={15} /></button><button className="mini-action" onClick={() => void toggleCategory(item)} aria-label="تغيير حالة التصنيف">{item.is_active ? <ToggleRight size={17} /> : <ToggleLeft size={17} />}</button></> : null}
                </ReferenceRow>
              ))}
            </ReferenceSection>
          </> : null}
        </section>
      ) : null}
    </AppShell>
  );
}

function ReferenceSection({
  icon,
  title,
  subtitle,
  form,
  children,
}: {
  icon: ReactNode;
  title: string;
  subtitle: string;
  form: ReactNode;
  children: ReactNode;
}) {
  return (
    <article className="panel reference-panel">
      <header className="panel__head"><div><h3>{title}</h3><p>{subtitle}</p></div>{icon}</header>
      {form}
      <div className="reference-list">{children}</div>
    </article>
  );
}

function ReferenceRow({
  code,
  name,
  active,
  badge,
  children,
}: {
  code: string;
  name: string;
  active: boolean;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <div className={`reference-row ${active ? "" : "reference-row--inactive"}`}>
      <span className="reference-row__code" dir="ltr">{code}</span>
      <span><strong>{name}</strong><small>{active ? "نشط" : "غير نشط"}</small></span>
      {badge ? <span className="status-badge status-badge--system">{badge}</span> : null}
      <span className="reference-row__actions">{children}</span>
    </div>
  );
}
