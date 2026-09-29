import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Warehouse = { id: string; code: string; name_ar: string; is_default: boolean; is_active: boolean };

export function WarehousePage() {
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await api<Warehouse[]>("/master-data/warehouses");
      const factory = rows.filter((item) => item.is_default || item.code === "MAIN").slice(0, 1);
      setWarehouses(factory.length ? factory : rows.slice(0, 1));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل إعداد المخزن");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return <AppShell>
    <section className="page-heading"><div><h2>إعداد المخزن</h2><p>المخزن الحالي هو المصنع. كل حركات الشراء والبيع والتسوية تسجل عليه.</p></div><button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17} /> تحديث</button></section>
    {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
    <section className="panel">{warehouses.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>الكود</th><th>الاسم</th></tr></thead><tbody>{warehouses.map((item) => <tr key={item.id}><td dir="ltr">{item.code}</td><td>{item.name_ar}</td></tr>)}</tbody></table></div> : <div className="empty-state"><h4>لا يوجد مخزن مصنع مفعّل</h4></div>}</section>
  </AppShell>;
}
