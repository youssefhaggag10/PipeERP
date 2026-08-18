import { Boxes, Check, PackagePlus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Unit = {
  id: string;
  code: string;
  name_ar: string;
  symbol: string;
};

type Product = {
  id: string;
  code: string;
  name_ar: string;
  product_type: "raw_material" | "finished_good" | "waste" | "service" | "spare_part";
  unit_id: string;
  min_stock: string;
  track_lots: boolean;
  standard_weight_kg: string;
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [productType, setProductType] = useState<Product["product_type"]>("raw_material");
  const [unitId, setUnitId] = useState("");
  const [minStock, setMinStock] = useState("0");
  const [standardWeight, setStandardWeight] = useState("0");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [productRows, unitRows] = await Promise.all([
        api<Product[]>("/master-data/products"),
        api<Unit[]>("/master-data/units"),
      ]);
      setProducts(productRows);
      setUnits(unitRows);
      setUnitId((current) => current || unitRows[0]?.id || "");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل المنتجات");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createProduct(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api<Product>("/master-data/products", {
        method: "POST",
        body: JSON.stringify({
          code,
          name_ar: name,
          product_type: productType,
          unit_id: unitId,
          min_stock: minStock,
          track_lots: productType !== "service",
          standard_weight_kg: standardWeight,
          weight_tolerance_percent: "5",
        }),
      });
      setCode("");
      setName("");
      setMinStock("0");
      setStandardWeight("0");
      setNotice("تم إنشاء المنتج وتسجيل العملية في سجل التدقيق.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء المنتج");
    }
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
          {products.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>الكود</th><th>المنتج</th><th>النوع</th><th>الوحدة</th><th>الحد الأدنى</th><th>الوزن القياسي</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td dir="ltr">{product.code}</td><td><strong>{product.name_ar}</strong></td><td><span className="status-badge status-badge--system">{typeLabels[product.product_type]}</span></td><td>{units.find((unit) => unit.id === product.unit_id)?.symbol ?? "—"}</td><td>{product.min_stock}</td><td>{product.standard_weight_kg} كجم</td></tr>)}</tbody></table></div> : <div className="empty-state"><span className="empty-state__icon"><Boxes size={27} /></span><h4>لا توجد منتجات بعد</h4><p>أضف أول خامة أو منتج تام لبدء تشغيل المخزون.</p></div>}
        </article>

        {canManage ? <article className="panel master-form-card"><header className="panel__head"><div><h3>منتج جديد</h3><p>الأكواد غير قابلة للتكرار حتى مع اختلاف حالة الأحرف</p></div></header><form className="compact-form" onSubmit={createProduct}><label>كود المنتج<input dir="ltr" value={code} onChange={(event) => setCode(event.target.value)} placeholder="RM-001" required /></label><label>اسم المنتج<input value={name} onChange={(event) => setName(event.target.value)} required minLength={2} /></label><label>نوع المنتج<select value={productType} onChange={(event) => setProductType(event.target.value as Product["product_type"])}>{Object.entries(typeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>وحدة القياس<select value={unitId} onChange={(event) => setUnitId(event.target.value)} required>{units.map((unit) => <option value={unit.id} key={unit.id}>{unit.name_ar} ({unit.symbol})</option>)}</select></label><label>الحد الأدنى للمخزون<input type="number" min="0" step="0.001" value={minStock} onChange={(event) => setMinStock(event.target.value)} required /></label><label>الوزن القياسي بالكيلو<input type="number" min="0" step="0.001" value={standardWeight} onChange={(event) => setStandardWeight(event.target.value)} required /></label><button className="primary-button"><PackagePlus size={17} /> حفظ المنتج</button></form></article> : null}
      </section>
    </AppShell>
  );
}
