import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpLeft,
  Boxes,
  Factory,
  PackageCheck,
  Plus,
  Scale,
  ShoppingCart,
  TrendingUp,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api } from "../lib/api";
import { firstManageableAction, visibleDashboardActions } from "./dashboardActions";

type DashboardSummary = {
  sales_today: string | null;
  open_manufacturing_orders: number | null;
  low_stock_products: number | null;
  weight_sold_today_kg: string | null;
  activity: Array<{
    document_number: string;
    module: "sales" | "purchases" | "manufacturing";
    status: string;
    occurred_at: string;
    route: string;
  }>;
};

const number = new Intl.NumberFormat("ar-EG", { maximumFractionDigits: 2 });
const moduleLabels = { sales: "مبيعات", purchases: "مشتريات", manufacturing: "تصنيع" };

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const permissions = user?.permissions ?? [];
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const actions = visibleDashboardActions(permissions);
  const primaryAction = firstManageableAction(permissions);
  const firstModuleRoute = actions[0]?.to.split("?")[0];
  const actionIcons = {
    "أمر بيع": ShoppingCart,
    "استلام مشتريات": PackageCheck,
    "أمر تصنيع": Factory,
    "كارت صنف": Boxes,
  } as const;
  const metrics = [
    { label: "مبيعات اليوم", value: summary?.sales_today == null ? "—" : number.format(Number(summary.sales_today)), unit: "ج.م", icon: TrendingUp, tone: "green" },
    { label: "أوامر تحت التشغيل", value: summary?.open_manufacturing_orders ?? "—", unit: "أمر", icon: Factory, tone: "blue" },
    { label: "تنبيهات المخزون", value: summary?.low_stock_products ?? "—", unit: "صنف", icon: Boxes, tone: "amber" },
    { label: "وزن مباع اليوم", value: summary?.weight_sold_today_kg == null ? "—" : number.format(Number(summary.weight_sold_today_kg)), unit: "كجم", icon: Scale, tone: "violet" },
  ];

  useEffect(() => {
    void api<DashboardSummary>("/dashboard/summary").then(setSummary).catch(() => setSummary(null));
  }, []);

  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <span className="eyebrow">ملخص التشغيل</span>
          <h2>ماذا يحدث في المصنع الآن؟</h2>
          <p>متابعة يومية مركّزة لأهم العمليات التي تحتاج انتباهك.</p>
        </div>
        <button
          className="primary-button primary-button--compact"
          disabled={!primaryAction}
          onClick={() => primaryAction && navigate(primaryAction.to)}
        >
          <Plus size={18} />
          <span>عملية جديدة</span>
        </button>
      </section>

      <section className="metrics-grid" aria-label="مؤشرات اليوم">
        {metrics.map(({ label, value, unit, icon: Icon, tone }) => (
          <article className="metric-card" key={label}>
            <span className={`metric-card__icon metric-card__icon--${tone}`}>
              <Icon size={21} strokeWidth={1.8} />
            </span>
            <span className="metric-card__label">{label}</span>
            <p><strong>{value}</strong><small>{unit}</small></p>
            <span className="metric-card__hint">محدّث من العمليات المرحلة</span>
          </article>
        ))}
      </section>

      <section className="dashboard-grid">
        <article className="panel panel--wide">
          <header className="panel__head">
            <div>
              <h3>حركة التشغيل</h3>
              <p>آخر المستندات التي تغيّرت حالتها</p>
            </div>
            <button
              className="text-button"
              disabled={!firstModuleRoute}
              onClick={() => firstModuleRoute && navigate(firstModuleRoute)}
            >عرض الوحدات <ArrowLeft size={16} /></button>
          </header>
          {summary?.activity.length ? <div className="dashboard-activity-list">{summary.activity.map((item) => <button key={`${item.module}-${item.document_number}`} onClick={() => navigate(item.route)}><span className="purchase-order-card__icon">{item.module === "sales" ? <ShoppingCart size={17} /> : item.module === "purchases" ? <PackageCheck size={17} /> : <Factory size={17} />}</span><span><strong dir="ltr">{item.document_number}</strong><small>{moduleLabels[item.module]} · {new Date(item.occurred_at).toLocaleString("ar-EG")}</small></span><span className="status-badge status-badge--system">{item.status}</span><ArrowLeft size={16} /></button>)}</div> : <div className="empty-state">
            <span className="empty-state__icon"><PackageCheck size={27} /></span>
            <h4>مساحة العمل جاهزة</h4>
            <p>ستظهر هنا أوامر البيع والشراء والتصنيع فور تسجيل أول عملية.</p>
          </div>}
        </article>

        <article className="panel attention-panel">
          <header className="panel__head">
            <div>
              <h3>يحتاج انتباهك</h3>
              <p>تنبيهات تشغيلية وليست مجرد إشعارات</p>
            </div>
          </header>
          <button className="attention-item" onClick={() => summary?.low_stock_products ? navigate("/inventory") : undefined}>
            <span className="attention-item__icon"><AlertTriangle size={19} /></span>
            <div><strong>{summary?.low_stock_products ? `${summary.low_stock_products} صنف تحت الحد الأدنى` : "لا توجد تنبيهات حاليًا"}</strong><small>{summary?.low_stock_products ? "افتح المخزون لمراجعة الأرصدة" : "سنرتبها حسب درجة التأثير"}</small></div>
            <ArrowUpLeft size={17} />
          </button>
        </article>
      </section>

      <section className="quick-actions">
        <header className="section-title">
          <h3>إجراءات سريعة</h3>
          <p>ابدأ العملية مباشرة دون البحث داخل القوائم.</p>
        </header>
        {actions.length ? <div className="quick-actions__grid">
          {actions.map((action) => {
            const Icon = actionIcons[action.label as keyof typeof actionIcons];
            const disabled = action.managePermission ? !permissions.includes(action.managePermission) : false;
            return <button key={action.label} disabled={disabled} onClick={() => navigate(action.to)} title={disabled ? "ليس لديك صلاحية تنفيذ هذه العملية" : undefined}>
              <Icon size={21} /><span><strong>{action.label}</strong><small>{action.description}</small></span><ArrowLeft size={17} />
            </button>;
          })}
        </div> : <div className="empty-state empty-state--compact"><h4>لا توجد وحدات تشغيل متاحة</h4><p>اطلب من مدير النظام منحك صلاحية الوحدة المطلوبة.</p></div>}
      </section>
    </AppShell>
  );
}
