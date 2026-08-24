import {
  AlertTriangle,
  Boxes,
  CircleDollarSign,
  PackageCheck,
  Recycle,
  Warehouse,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AppShell } from "../components/AppShell";
import { api } from "../lib/api";

type DashboardSummary = {
  total_products: number;
  products_with_stock: number;
  raw_material_balance: string;
  finished_good_balance: string;
  waste_balance: string;
  inventory_value: string;
  low_stock_products: number;
};

const number = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 2 });

export function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    void api<DashboardSummary>("/dashboard/summary")
      .then(setSummary)
      .catch(() => setSummary(null));
  }, []);

  const metrics = [
    { label: "إجمالي الأصناف", value: summary?.total_products ?? "—", icon: Boxes, tone: "green" },
    { label: "أصناف لها رصيد", value: summary?.products_with_stock ?? "—", icon: PackageCheck, tone: "blue" },
    { label: "رصيد الخامات", value: summary ? number.format(Number(summary.raw_material_balance)) : "—", icon: Warehouse, tone: "amber" },
    { label: "رصيد المنتجات", value: summary ? number.format(Number(summary.finished_good_balance)) : "—", icon: PackageCheck, tone: "violet" },
    { label: "رصيد الهالك", value: summary ? number.format(Number(summary.waste_balance)) : "—", icon: Recycle, tone: "amber" },
    { label: "قيمة المخزون", value: summary ? number.format(Number(summary.inventory_value)) : "—", unit: "ج.م", icon: CircleDollarSign, tone: "green" },
    { label: "نقص المخزون", value: summary?.low_stock_products ?? "—", icon: AlertTriangle, tone: "amber" },
  ];

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <span className="eyebrow">الرئيسية</span>
          <h2>مؤشرات المخزون</h2>
          <p>نفس ملخص نسخة الديسكتوب.</p>
        </div>
      </section>
      <section className="metrics-grid" aria-label="مؤشرات المخزون">
        {metrics.map(({ label, value, unit, icon: Icon, tone }) => (
          <article className="metric-card" key={label}>
            <span className={`metric-card__icon metric-card__icon--${tone}`}>
              <Icon size={21} strokeWidth={1.8} />
            </span>
            <span className="metric-card__label">{label}</span>
            <p>
              <strong>{value}</strong>
              {unit ? <small>{unit}</small> : null}
            </p>
          </article>
        ))}
      </section>
    </AppShell>
  );
}
