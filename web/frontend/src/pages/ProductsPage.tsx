import {
  Boxes,
  Check,
  PackagePlus,
  Pencil,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
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

type Product = {
  id: string;
  code: string;
  name_ar: string;
  product_type:
    "raw_material" | "finished_good" | "waste" | "service" | "spare_part";
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
  finished_good: "منتج نهائي",
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
  const [productType, setProductType] =
    useState<Product["product_type"]>("raw_material");
  const [unitId, setUnitId] = useState("");
  const [minStock, setMinStock] = useState("0");
  const [standardWeight, setStandardWeight] = useState("0");
  const [editing, setEditing] = useState<Product | null>(null);

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
      setError(
        reason instanceof ApiError ? reason.message : "تعذر تحميل المنتجات",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveProduct(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await api<Product>(
        editing
          ? `/master-data/products/${editing.id}`
          : "/master-data/products",
        {
          method: editing ? "PATCH" : "POST",
          body: JSON.stringify({
            ...(editing ? { version: editing.version } : {}),
            code,
            name_ar: name,
            product_type: productType,
            unit_id: unitId,
            category_id: null,
            clear_category: true,
            min_stock: minStock,
            track_lots: true,
            standard_weight_kg:
              productType === "finished_good" ? standardWeight : "0",
            weight_tolerance_percent: "0",
          }),
        },
      );
      resetForm();
      setNotice(
        editing
          ? "تم تحديث المنتج وتسجيل العملية في سجل التدقيق."
          : "تم إنشاء المنتج وتسجيل العملية في سجل التدقيق.",
      );
      await load();
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "تعذر إنشاء المنتج",
      );
    }
  }

  function resetForm() {
    setEditing(null);
    setCode("");
    setName("");
    setProductType("raw_material");
    setUnitId(
      units.find((unit) => unit.is_active !== false)?.id ?? units[0]?.id ?? "",
    );
    setMinStock("0");
    setStandardWeight("0");
  }

  function editProduct(item: Product) {
    setEditing(item);
    setCode(item.code);
    setName(item.name_ar);
    setProductType(item.product_type);
    setUnitId(item.unit_id);
    setMinStock(item.min_stock);
    setStandardWeight(item.standard_weight_kg);
  }

  async function deleteProduct(item: Product) {
    if (!window.confirm(`هل تريد حذف الصنف: ${item.name_ar}؟`)) return;
    setError("");
    setNotice("");
    try {
      await api(`/master-data/products/${item.id}`, { method: "DELETE" });
      if (editing?.id === item.id) resetForm();
      setNotice("تم حذف الصنف.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر حذف الصنف");
    }
  }

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <h2>الأصناف</h2>
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
              <h3>الأصناف</h3>
              <p>{products.length} صنفًا</p>
            </div>
          </header>
          {products.length ? (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>الكود</th>
                    <th>الاسم</th>
                    <th>النوع</th>
                    <th>الوحدة</th>
                    <th>الوزن القياسي كجم</th>
                    <th>حد التنبيه</th>
                    {canManage ? <th>إجراء</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.id}>
                      <td dir="ltr">{product.code}</td>
                      <td>
                        <strong>{product.name_ar}</strong>
                      </td>
                      <td>{typeLabels[product.product_type]}</td>
                      <td>
                        {units.find((unit) => unit.id === product.unit_id)
                          ?.symbol ?? "—"}
                      </td>
                      <td>
                        {product.product_type === "finished_good"
                          ? product.standard_weight_kg
                          : "0"}
                      </td>
                      <td>{product.min_stock}</td>
                      {canManage ? (
                        <td>
                          <div className="table-actions">
                            <button
                              className="mini-action"
                              onClick={() => editProduct(product)}
                              aria-label="تعديل الصنف"
                            >
                              <Pencil size={15} />
                            </button>
                            <button
                              className="mini-action danger-button product-delete-action"
                              onClick={() => void deleteProduct(product)}
                              aria-label="حذف الصنف"
                            >
                              <Trash2 size={15} />
                              <span>حذف</span>
                            </button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-state__icon">
                <Boxes size={27} />
              </span>
              <h4>لا توجد أصناف بعد</h4>
            </div>
          )}
        </article>

        {canManage ? (
          <article className="panel master-form-card">
            <header className="panel__head">
              <div>
                <h3>{editing ? "تعديل الصنف" : "صنف جديد"}</h3>
              </div>
            </header>
            <form className="compact-form" onSubmit={saveProduct}>
              <label>
                الكود
                <input
                  dir="ltr"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="RM-001"
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
                النوع
                <select
                  value={productType}
                  onChange={(event) => {
                    const value = event.target.value as Product["product_type"];
                    setProductType(value);
                    if (value !== "finished_good") setStandardWeight("0");
                  }}
                >
                  {Object.entries(typeLabels).map(([value, label]) => (
                    <option value={value} key={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                الوحدة
                <select
                  value={unitId}
                  onChange={(event) => setUnitId(event.target.value)}
                  required
                >
                  {units.map((unit) => (
                    <option value={unit.id} key={unit.id}>
                      {unit.name_ar} ({unit.symbol})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                حد التنبيه
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={minStock}
                  onChange={(event) => setMinStock(event.target.value)}
                  required
                />
              </label>
              <label>
                وزن القطعة القياسي (كجم)
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={standardWeight}
                  onChange={(event) => setStandardWeight(event.target.value)}
                  disabled={productType !== "finished_good"}
                  required
                />
              </label>
              <div className="form-actions">
                <button className="primary-button">
                  <PackagePlus size={17} />{" "}
                  {editing ? "حفظ تعديلات الصنف" : "حفظ الصنف"}
                </button>
                {editing ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={resetForm}
                  >
                    <X size={16} /> إلغاء التعديل
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
