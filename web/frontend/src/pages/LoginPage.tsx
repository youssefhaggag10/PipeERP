import { ArrowLeft, Eye, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { BrandMark } from "../components/BrandMark";
import { ApiError } from "../lib/api";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const authenticated = await login(username, password);
      const requested = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(authenticated.must_change_password ? "/change-password" : requested, { replace: true });
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تسجيل الدخول");
    } finally {
      setSubmitting(false);
    }
  }

  if (user) return <Navigate to={user.must_change_password ? "/change-password" : "/"} replace />;

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <BrandMark />
        <div className="login-panel__intro">
          <span className="eyebrow">منظومة إدارة المصنع</span>
          <h1 id="login-title">مرحبًا بعودتك</h1>
          <p>سجّل الدخول للوصول إلى مساحة العمل والعمليات المصرّح لك بها.</p>
        </div>

        <form className="login-form" onSubmit={submit} aria-describedby={error ? "login-error" : undefined}>
          <label className="field">
            <span>اسم المستخدم</span>
            <span className="field__control">
              <UserRound size={19} />
              <input
                name="username"
                autoComplete="username"
                placeholder="أدخل اسم المستخدم"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
                autoFocus
              />
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
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
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
          {error ? <p className="form-error" id="login-error" role="alert">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={submitting}>
            <span>{submitting ? "جارٍ التحقق…" : "تسجيل الدخول"}</span>
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
