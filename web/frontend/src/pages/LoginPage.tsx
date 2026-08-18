import { ArrowLeft, Eye, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";

import { BrandMark } from "../components/BrandMark";

export function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <BrandMark />
        <div className="login-panel__intro">
          <span className="eyebrow">منظومة إدارة المصنع</span>
          <h1 id="login-title">مرحبًا بعودتك</h1>
          <p>سجّل الدخول للوصول إلى مساحة العمل والعمليات المصرّح لك بها.</p>
        </div>

        <form className="login-form" onSubmit={submit}>
          <label className="field">
            <span>اسم المستخدم</span>
            <span className="field__control">
              <UserRound size={19} />
              <input name="username" autoComplete="username" placeholder="أدخل اسم المستخدم" />
            </span>
          </label>
          <label className="field">
            <span>كلمة المرور</span>
            <span className="field__control">
              <LockKeyhole size={19} />
              <input
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="أدخل كلمة المرور"
              />
              <button
                type="button"
                className="field__action"
                aria-label={showPassword ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
                onClick={() => setShowPassword((value) => !value)}
              >
                <Eye size={18} />
              </button>
            </span>
          </label>
          <button className="primary-button" type="submit">
            <span>تسجيل الدخول</span>
            <ArrowLeft size={19} />
          </button>
        </form>

        <div className="security-note">
          <ShieldCheck size={18} />
          <span>اتصال آمن ومراقبة كاملة للعمليات الحساسة</span>
        </div>
      </section>

      <aside className="login-visual" aria-hidden="true">
        <div className="login-visual__grid" />
        <div className="login-visual__content">
          <p className="login-visual__kicker">تشغيل مترابط</p>
          <h2>من الخامة إلى المنتج النهائي.</h2>
          <p>رؤية واحدة للمخزون والتصنيع والمبيعات والتكلفة، بدون فقد التفاصيل.</p>
          <div className="flow-card">
            <span>الخامات</span><i />
            <span>التصنيع</span><i />
            <span>المنتج التام</span>
          </div>
        </div>
        <div className="pipe-orbit pipe-orbit--one" />
        <div className="pipe-orbit pipe-orbit--two" />
      </aside>
    </main>
  );
}
