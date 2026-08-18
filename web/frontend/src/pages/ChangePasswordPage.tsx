import { KeyRound, LogOut, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { BrandMark } from "../components/BrandMark";
import { api, ApiError } from "../lib/api";

export function ChangePasswordPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setError("كلمتا المرور الجديدتان غير متطابقتين");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      await logout();
      navigate("/login", { replace: true });
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تغيير كلمة المرور");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="password-page">
      <section className="password-card">
        <BrandMark />
        <span className="password-card__icon"><ShieldCheck size={27} /></span>
        <h1>تأمين حسابك</h1>
        <p>عيّن كلمة مرور خاصة بك قبل متابعة استخدام النظام.</p>
        <form className="login-form" onSubmit={submit}>
          <label className="field"><span>كلمة المرور الحالية</span><span className="field__control"><KeyRound size={18} /><input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></span></label>
          <label className="field"><span>كلمة المرور الجديدة</span><span className="field__control"><KeyRound size={18} /><input type="password" autoComplete="new-password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></span></label>
          <label className="field"><span>تأكيد كلمة المرور</span><span className="field__control"><KeyRound size={18} /><input type="password" autoComplete="new-password" minLength={12} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></span></label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button" disabled={submitting}>{submitting ? "جارٍ الحفظ…" : "حفظ وتسجيل الدخول مجددًا"}</button>
        </form>
        <button className="text-button password-card__logout" onClick={() => void logout()}><LogOut size={16} /> تسجيل الخروج</button>
      </section>
    </main>
  );
}
