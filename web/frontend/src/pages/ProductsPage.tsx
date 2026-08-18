import { Boxes, Check, PackagePlus, Pencil, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Unit = {
  id: string;
  code: string;
  name_ar: string;
  symbol: string;
  is_active: boolean;
};

type Category = {
  id: string;
  name_ar: string;
  is_active: boolean;
};

type Product = {
  id: string;
  code: string;
  name_ar: string;
  product_type: "raw_material" | "finished_good" | "waste" | "service" | "spare_part";
  unit_id: string;
  category_id: string | null;
  min_stock: string;
  track_lots: boolean;
  standard_weight_kg: string;
  weight_tolerance_percent: string;
  is_active: boolean;
  version: number;
};

const typeLabels: Record<Product["product_type"], string> = {
  raw_material: "خامة",
  finished_good: "منتج تام",
  waste: "هالك",
  service: "خدمة",
  spare_part: "قطعة غيار",
};

export function ProductsPage() {
  const { user } = useAuth();
  const canManage = user?.permissions.includes("products.manage") ?? false;
  const [products, setProducts] = useState<Product[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [productType, setProductType] = useState<Product["product_type"]>("raw_material");
  const [unitId, setUnitId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [minStock, setMinStock] = useState("0");
  const [standardWeight, setStandardWeight] = useState("0");
  const [weightTolerance, setWeightTolerance] = useState("5");
  const [trackLots, setTrackLots] = useState(true);
  const [isActive, setIsActive] = useState(true);
  const [editing, setEditing] = useState<Product | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const suffix = canManage ? "?include_inactive=true" : "";
      const [productRows, unitRows, categoryRows] = await Promise.all([
        api<Product[]>(`/master-data/products${suffix}`),
        api<Unit[]>(`/master-data/units${suffix}`),
        api<Category[]>(`/master-data/categories${suffix}`),
      ]);
      setProducts(productRows);
      setUnits(unitRows);
      setCategories(categoryRows);
      setUnitId((current) => current || unitRows[0]?.id || "");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل المنتجات");
    } finally {
      setLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveProduct(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api<Product>(editing ? `/master-data/products/${editing.id}` : "/master-data/products", {
        method: editing ? "PATCH" : "POST",
        body: JSON.stringify({
          ...(editing ? { version: editing.version } : {}),
          code,
          name_ar: name,
          product_type: productType,
          unit_id: unitId,
          category_id: categoryId || null,
          clear_category: !categoryId,
          min_stock: minStock,
          track_lots: trackLots,
          standard_weight_kg: standardWeight,
          weight_tolerance_percent: weightTolerance,
          ...(editing ? { is_active: isActive } : {}),
        }),
      });
      resetForm();
      setNotice(editing ? "تم تحديث المنتج وتسجيل العملية في سجل التدقيق." : "تم إنشاء المنتج وتسجيل العملية في سجل التدقيق.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء المنتج");
    }
  }

  function resetForm() {
    setEditing(null);
    setCode("");
    setName("");
    setProductType("raw_material");
    setUnitId(units.find((unit) => unit.is_active !== false)?.id ?? units[0]?.id ?? "");
    setCategoryId("");
    setMinStock("0");
    setStandardWeight("0");
    setWeightTolerance("5");
    setTrackLots(true);
    setIsActive(true);
  }

  function editProduct(item: Product) {
    setEditing(item);
    setCode(item.code);
    setName(item.name_ar);
    setProductType(item.product_type);
    setUnitId(item.unit_id);
    setCategoryId(item.category_id ?? "");
    setMinStock(item.min_stock);
    setStandardWeight(item.standard_weight_kg);
    setWeightTolerance(item.weight_tolerance_percent);
    setTrackLots(item.track_lots);
    setIsActive(item.is_active);
  }

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <span className="eyebrow">البيانات الأساسية</span>
          <h2>المنتجات والأصناف</h2>
          <p>تعريف الخامات والمنتجات التامة ووحدات القياس وخصائص الوزن.</p>
        </div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={17} /> تحديث
        </button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      <section className={`master-layout ${canManage ? "" : "master-layout--single"}`}>
        <article className="panel">
          <header className="panel__head">
            <div><h3>دليل المنتجات</h3><p>{products.length} صنفًا نشطًا</p></div>
          </header>
          {products.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>الكود</th><th>المنتج</th><th>النوع</th><th>الوحدة</th><th>الحد الأدنى</th><th>الوزن القياسي</th><th>الحالة</th>{canManage ? <th>إجراء</th> : null}</tr></thead><tbody>{products.map((product) => <tr key={product.id}><td dir="ltr">{product.code}</td><td><strong>{product.name_ar}</strong></td><td><span className="status-badge status-badge--system">{typeLabels[product.product_type]}</span></td><td>{units.find((unit) => unit.id === product.unit_id)?.symbol ?? "—"}</td><td>{product.min_stock}</td><td>{product.standard_weight_kg} كجم</td><td><span className={`status-badge ${product.is_active ? "status-badge--active" : ""}`}>{product.is_active ? "نشط" : "متوقف"}</span></td>{canManage ? <td><button className="mini-action" onClick={() => editProduct(product)} aria-label="تعديل المنتج"><Pencil size={15} /></button></td> : null}</tr>)}</tbody></table></div> : <div className="empty-state"><span className="empty-state__icon"><Boxes size={27} /></span><h4>لا توجد منتجات بعد</h4><p>أضف أول خامة أو منتج تام لبدء تشغيل المخزون.</p></div>}
        </article>

        {canManage ? <article className="panel master-form-card"><header className="panel__head"><div><h3>{editing ? "تعديل المنتج" : "منتج جديد"}</h3><p>الأكواد غير قابلة للتكرار حتى مع اختلاف حالة الأحرف</p></div></header><form className="compact-form" onSubmit={saveProduct}><label>كود المنتج<input dir="ltr" value={code} onChange={(event) => setCode(event.target.value)} placeholder="RM-001" required /></label><label>اسم المنتج<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} /></label><label>نوع المنتج<select value={productType} onChange={(event) => { const value = event.target.value as Product["product_type"]; setProductType(value); if (value === "service") setTrackLots(false); }}>{Object.entries(typeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>وحدة القياس<select value={unitId} onChange={(event) => setUnitId(event.target.value)} required>{units.map((unit) => <option value={unit.id} key={unit.id}>{unit.name_ar} ({unit.symbol})</option>)}</select></label><label>التصنيف<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="">بدون تصنيف</option>{categories.filter((item) => item.is_active || item.id === categoryId).map((item) => <option value={item.id} key={item.id}>{item.name_ar}</option>)}</select></label><label>الحد الأدنى للمخزون<input type="number" min="0" step="0.001" value={minStock} onChange={(event) => setMinStock(event.target.value)} required /></label><label>الوزن القياسي بالكيلو<input type="number" min="0" step="0.001" value={standardWeight} onChange={(event) => setStandardWeight(event.target.value)} required /></label><label>سماحية الوزن %<input type="number" min="0" max="100" step="0.001" value={weightTolerance} onChange={(event) => setWeightTolerance(event.target.value)} required /></label><label className="check-field"><input type="checkbox" checked={trackLots} onChange={(event) => setTrackLots(event.target.checked)} /> تتبع التشغيلات</label>{editing ? <label className="check-field"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /> المنتج نشط</label> : null}<div className="form-actions"><button className="primary-button"><PackagePlus size={17} /> {editing ? "حفظ التعديل" : "حفظ المنتج"}</button>{editing ? <button type="button" className="secondary-button" onClick={resetForm}><X size={16} /> إلغاء</button> : null}</div></form></article> : null}
      </section>
    </AppShell>
  );
}
