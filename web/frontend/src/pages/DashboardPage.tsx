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

import { AppShell } from "../components/AppShell";

const metrics = [
  { label: "مبيعات اليوم", value: "—", unit: "ج.م", icon: TrendingUp, tone: "green" },
  { label: "أوامر تحت التشغيل", value: "—", unit: "أمر", icon: Factory, tone: "blue" },
  { label: "تنبيهات المخزون", value: "—", unit: "صنف", icon: Boxes, tone: "amber" },
  { label: "وزن مباع اليوم", value: "—", unit: "كجم", icon: Scale, tone: "violet" },
];

export function DashboardPage() {
  return (
    <AppShell>
      <section className="page-heading">
        <div>
          <span className="eyebrow">ملخص التشغيل</span>
          <h2>ماذا يحدث في المصنع الآن؟</h2>
          <p>متابعة يومية مركّزة لأهم العمليات التي تحتاج انتباهك.</p>
        </div>
        <button className="primary-button primary-button--compact">
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
            <span className="metric-card__hint">تظهر القيمة بعد بدء التشغيل</span>
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
            <button className="text-button">عرض الكل <ArrowLeft size={16} /></button>
          </header>
          <div className="empty-state">
            <span className="empty-state__icon"><PackageCheck size={27} /></span>
            <h4>مساحة العمل جاهزة</h4>
            <p>ستظهر هنا أوامر البيع والشراء والتصنيع فور تسجيل أول عملية.</p>
          </div>
        </article>

        <article className="panel attention-panel">
          <header className="panel__head">
            <div>
              <h3>يحتاج انتباهك</h3>
              <p>تنبيهات تشغيلية وليست مجرد إشعارات</p>
            </div>
          </header>
          <div className="attention-item">
            <span className="attention-item__icon"><AlertTriangle size={19} /></span>
            <div><strong>لا توجد تنبيهات حاليًا</strong><small>سنرتبها حسب درجة التأثير</small></div>
            <ArrowUpLeft size={17} />
          </div>
        </article>
      </section>

      <section className="quick-actions">
        <header className="section-title">
          <h3>إجراءات سريعة</h3>
          <p>ابدأ العملية مباشرة دون البحث داخل القوائم.</p>
        </header>
        <div className="quick-actions__grid">
          <button><ShoppingCart size={21} /><span><strong>أمر بيع</strong><small>بالقطعة أو الوزن</small></span><ArrowLeft size={17} /></button>
          <button><PackageCheck size={21} /><span><strong>استلام مشتريات</strong><small>إضافة مخزون وتكلفة</small></span><ArrowLeft size={17} /></button>
          <button><Factory size={21} /><span><strong>أمر تصنيع</strong><small>تخطيط خلطة جديدة</small></span><ArrowLeft size={17} /></button>
          <button><Boxes size={21} /><span><strong>كارت صنف</strong><small>تتبّع الحركة والرصيد</small></span><ArrowLeft size={17} /></button>
        </div>
      </section>
    </AppShell>
  );
}
