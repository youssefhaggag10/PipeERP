import { AlertTriangle, Check, DatabaseBackup, Download, Image, MonitorCog, Plus, Printer, RefreshCw, Save, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { type AuthUser, useAuth } from "../auth/AuthContext";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Tab = "print" | "watermark" | "appearance" | "backup" | "users" | "reset";
type CompanySettings = {
  company_name_ar: string;
  phone: string;
  address: string;
  tax_number: string;
  currency_code: string;
  currency_decimal_places: number;
  tax_enabled: boolean;
  default_tax_rate: string;
  default_warehouse_id: string | null;
  version: number;
};
type AppearanceSettings = {
  theme: "system" | "light" | "dark";
  fontSize: number;
  scale: number;
};
type HeaderLogoSettings = { image: string };
type Role = {
  id: string;
  code: string;
  name_ar: string;
  permissions: string[];
};

const appearanceKey = "pipeerp.appearance";
const headerLogoKey = "pipeerp.header-logo";

function readHeaderLogo(): HeaderLogoSettings {
  try {
    const saved = JSON.parse(
      localStorage.getItem(headerLogoKey)
        ?? localStorage.getItem("pipeerp.watermark")
        ?? "null",
    ) as Partial<HeaderLogoSettings> | null;
    return { image: saved?.image ?? "" };
  } catch {
    return { image: "" };
  }
}

function readAppearance(): AppearanceSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(appearanceKey) ?? "null") as Partial<AppearanceSettings> | null;
    return {
      theme: saved?.theme === "light" || saved?.theme === "dark" ? saved.theme : "system",
      fontSize: Math.min(22, Math.max(10, Number(saved?.fontSize) || 14)),
      scale: Math.min(160, Math.max(70, Number(saved?.scale) || 100)),
    };
  } catch {
    return { theme: "system", fontSize: 14, scale: 100 };
  }
}

function applyAppearance(value: AppearanceSettings) {
  document.documentElement.dataset.theme = value.theme;
  document.documentElement.style.setProperty("--app-font-size", `${value.fontSize}px`);
  document.documentElement.style.setProperty("--app-scale", String(value.scale / 100));
  localStorage.setItem(appearanceKey, JSON.stringify(value));
}

type SettingsTabsProps = {
  tab: Tab;
  canManage: boolean;
  canReadUsers: boolean;
  isSystemAdmin: boolean;
  onSelect: (tab: Tab) => void;
};

function SettingsTabs({ tab, canManage, canReadUsers, isSystemAdmin, onSelect }: Readonly<SettingsTabsProps>) {
  const canManageSystem = isSystemAdmin && canManage;
  return <div className="sales-tabs settings-tabs" role="tablist">
    <button type="button" className={tab === "print" ? "active" : ""} onClick={() => onSelect("print")}><Printer size={17}/> الطباعة</button>
    <button type="button" className={tab === "watermark" ? "active" : ""} onClick={() => onSelect("watermark")}><Image size={17}/> شعار الهيدر</button>
    <button type="button" className={tab === "appearance" ? "active" : ""} onClick={() => onSelect("appearance")}><MonitorCog size={17}/> المظهر</button>
    {canManageSystem ? <button type="button" className={tab === "backup" ? "active" : ""} onClick={() => onSelect("backup")}><DatabaseBackup size={17}/> النسخ الاحتياطي</button> : null}
    {canReadUsers ? <button type="button" className={tab === "users" ? "active" : ""} onClick={() => onSelect("users")}><ShieldCheck size={17}/> المستخدمون والصلاحيات</button> : null}
    {canManageSystem ? <button type="button" className={tab === "reset" ? "active" : ""} onClick={() => onSelect("reset")}><AlertTriangle size={17}/> تصفير الحركات</button> : null}
  </div>;
}

type PrintSettingsPanelProps = {
  settings: CompanySettings;
  canManage: boolean;
  onChange: (settings: CompanySettings) => void;
  onSubmit: (event: FormEvent) => void;
};

function PrintSettingsPanel({ settings, canManage, onChange, onSubmit }: Readonly<PrintSettingsPanelProps>) {
  return <section className="panel settings-panel"><header className="panel__head"><div><h3>بيانات فاتورة المبيعات</h3><p>البيانات التي تظهر أعلى الفواتير وكشوف الحساب.</p></div><Printer size={20}/></header><form className="compact-form settings-print-form" onSubmit={onSubmit}>
    <label>اسم المنشأة<input value={settings.company_name_ar} disabled={!canManage} onChange={(event) => onChange({ ...settings, company_name_ar: event.target.value })} required/></label>
    <label>العنوان<input value={settings.address} disabled={!canManage} onChange={(event) => onChange({ ...settings, address: event.target.value })}/></label>
    <label>أرقام الشركة والمبيعات<textarea dir="ltr" rows={5} value={settings.phone} disabled={!canManage} placeholder="رقم في كل سطر؛ الرقم الأول هو الرئيسي" onChange={(event) => onChange({ ...settings, phone: event.target.value })}/></label>
    {canManage ? <button type="submit" className="primary-button"><Save size={17}/> حفظ إعدادات الفاتورة</button> : null}
  </form></section>;
}

type HeaderLogoPanelProps = {
  headerLogo: HeaderLogoSettings;
  onChoose: (file: File | undefined) => void;
  onClear: () => void;
  onSubmit: (event: FormEvent) => void;
};

function HeaderLogoPanel({ headerLogo, onChoose, onClear, onSubmit }: Readonly<HeaderLogoPanelProps>) {
  const preview = headerLogo.image
    ? <div className="watermark-preview"><img src={headerLogo.image} alt="معاينة شعار الهيدر"/><button type="button" className="mini-action" onClick={onClear}><Trash2 size={14}/> استخدام شعار النظام الافتراضي</button></div>
    : <p className="settings-note">سيُستخدم شعار PipeERP الافتراضي بجوار اسم المستخدم.</p>;
  return <section className="panel settings-panel"><header className="panel__head"><div><h3>شعار الهيدر الثابت</h3><p>يظهر دائمًا بجوار اسم المستخدم في الشريط العلوي بدل العلامة المائية داخل الصفحات.</p></div><Image size={20}/></header><form className="compact-form settings-print-form" onSubmit={onSubmit}>
    <label className="watermark-file"><span><Upload size={17}/> اختيار صورة اللوجو</span><input type="file" accept="image/png,image/jpeg,image/webp,image/bmp" onChange={(event) => onChoose(event.target.files?.[0])}/></label>
    {preview}
    <button type="submit" className="primary-button"><Save size={17}/> حفظ وتطبيق شعار الهيدر</button>
  </form></section>;
}

type AppearancePanelProps = {
  appearance: AppearanceSettings;
  onChange: (appearance: AppearanceSettings) => void;
  onSubmit: (event: FormEvent) => void;
};

function AppearancePanel({ appearance, onChange, onSubmit }: Readonly<AppearancePanelProps>) {
  return <section className="panel settings-panel"><header className="panel__head"><div><h3>الثيم وحجم واجهة البرنامج</h3><p>لا تؤثر هذه الإعدادات على تنسيق الفواتير المطبوعة.</p></div><MonitorCog size={20}/></header><form className="compact-form settings-print-form" onSubmit={onSubmit}>
    <label>الثيم<select value={appearance.theme} onChange={(event) => onChange({ ...appearance, theme: event.target.value as AppearanceSettings["theme"] })}><option value="system">حسب إعداد الجهاز</option><option value="light">فاتح</option><option value="dark">داكن</option></select></label>
    <div className="form-pair"><label>حجم الخط الأساسي<input type="number" min="10" max="22" value={appearance.fontSize} onChange={(event) => onChange({ ...appearance, fontSize: Number(event.target.value) })}/></label><label>تكبير العناصر والمسافات %<input type="number" min="70" max="160" value={appearance.scale} onChange={(event) => onChange({ ...appearance, scale: Number(event.target.value) })}/></label></div>
    <button type="submit" className="primary-button"><Save size={17}/> حفظ وتطبيق المظهر الآن</button>
  </form></section>;
}

function BackupPanel() {
  return <section className="panel settings-panel settings-backup"><DatabaseBackup size={36}/><h3>حماية بيانات PipeERP</h3><p>ينشئ النظام نسخة PostgreSQL كاملة تشمل البيانات والإعدادات، ثم ينزّلها على جهازك. احتفظ بها في مكان آمن.</p><a className="primary-button" href="/api/v1/system/backup" download><Download size={17}/> إنشاء وتنزيل نسخة احتياطية الآن</a></section>;
}

type UsersPanelProps = {
  currentUserId: string | undefined;
  canManageUsers: boolean;
  users: AuthUser[];
  roles: Role[];
  selectedUserId: string | null;
  username: string;
  displayName: string;
  password: string;
  role: string;
  active: boolean;
  onSelectUser: (user: AuthUser) => void;
  onUsernameChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onRoleChange: (value: string) => void;
  onActiveChange: (value: boolean) => void;
  onClear: () => void;
  onRemove: () => void;
  onSubmit: (event: FormEvent) => void;
};

function UsersPanel(props: Readonly<UsersPanelProps>) {
  const editingCurrentUser = props.selectedUserId === props.currentUserId;
  return <section className="settings-users-layout">
    <article className="panel settings-panel settings-users-table"><header className="panel__head"><div><h3>المستخدمون</h3><p>اختر مستخدمًا لتعديل بياناته وصلاحياته.</p></div><ShieldCheck size={20}/></header><div className="table-scroll"><table><thead><tr><th>الكود</th><th>اسم المستخدم</th><th>الاسم الكامل</th><th>الدور</th><th>الحالة</th></tr></thead><tbody>{props.users.map((item, index) => <tr key={item.id} className={props.selectedUserId === item.id ? "selected-row" : ""} onClick={() => props.onSelectUser(item)}><td>{index + 1}</td><td dir="ltr">{item.username}</td><td>{item.display_name}</td><td>{props.roles.find((role) => role.code === item.roles[0])?.name_ar ?? (item.roles.join("، ") || "بدون صلاحيات")}</td><td><span className={`status-badge ${item.is_active ? "status-badge--active" : ""}`}>{item.is_active ? "نشط" : "موقوف"}</span></td></tr>)}</tbody></table></div></article>
    <article className="panel settings-panel"><header className="panel__head"><div><h3>بيانات المستخدم</h3><p>{props.selectedUserId ? "تعديل المستخدم المحدد" : "إضافة مستخدم جديد"}</p></div></header><form className="compact-form settings-user-form" onSubmit={props.onSubmit}>
      <label>اسم المستخدم<input value={props.username} disabled={Boolean(props.selectedUserId) || !props.canManageUsers} onChange={(event) => props.onUsernameChange(event.target.value)} required/></label>
      <label>الاسم الكامل<input value={props.displayName} disabled={!props.canManageUsers} onChange={(event) => props.onDisplayNameChange(event.target.value)} required minLength={2}/></label>
      <label>كلمة المرور<input type="password" value={props.password} disabled={!props.canManageUsers} placeholder={props.selectedUserId ? "اتركها فارغة للاحتفاظ بالحالية" : "12 حرفًا على الأقل"} onChange={(event) => props.onPasswordChange(event.target.value)} required={!props.selectedUserId} minLength={12}/></label>
      <label>الدور<select value={props.role} disabled={!props.canManageUsers || editingCurrentUser} onChange={(event) => props.onRoleChange(event.target.value)}><option value="">بدون صلاحيات</option>{props.roles.map((role) => <option value={role.code} key={role.id}>{role.name_ar}</option>)}</select></label>
      <label className="check-row"><input type="checkbox" checked={props.active} disabled={!props.canManageUsers || editingCurrentUser} onChange={(event) => props.onActiveChange(event.target.checked)}/> مستخدم نشط</label>
      {props.canManageUsers ? <div className="settings-user-actions"><button type="submit" className="primary-button"><Save size={17}/> حفظ المستخدم والصلاحيات</button><button type="button" className="secondary-button" onClick={props.onClear}><Plus size={17}/> مستخدم جديد</button><button type="button" className="danger-button" disabled={!props.selectedUserId || editingCurrentUser} onClick={props.onRemove}><Trash2 size={17}/> حذف المستخدم</button></div> : null}
    </form></article>
  </section>;
}

type ResetPanelProps = {
  confirmation: string;
  password: string;
  onConfirmationChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
};

function ResetPanel({ confirmation, password, onConfirmationChange, onPasswordChange, onSubmit }: Readonly<ResetPanelProps>) {
  const resetDisabled = confirmation.trim() !== "تصفير النظام" || !password;
  return <section className="panel settings-panel settings-reset"><header className="panel__head"><div><h3>تصفير حركات النظام</h3><p>عملية خطرة ولا يمكن التراجع عنها إلا من نسخة احتياطية.</p></div><AlertTriangle size={24}/></header><div className="reset-warning">سيتم حذف أوامر وفواتير البيع والشراء، حركات المخزون والمدفوعات، أوامر التصنيع، المرتجعات، عروض الأسعار وبيانات CRM. سيتم الاحتفاظ بالأصناف والخلطات والعملاء والموردين والمخازن والحسابات المالية والمستخدمين والإعدادات والأرصدة الافتتاحية.</div><form className="compact-form settings-print-form" onSubmit={onSubmit}><label>اكتب «تصفير النظام» للتأكيد<input value={confirmation} onChange={(event) => onConfirmationChange(event.target.value)} required/></label><label>كلمة مرور الأدمن<input type="password" value={password} onChange={(event) => onPasswordChange(event.target.value)} required/></label><button type="submit" className="danger-button" disabled={resetDisabled}><Trash2 size={17}/> مسح الحركات وتصفير النظام</button></form></section>;
}

export function SettingsPage() {
  const { user } = useAuth();
  const canManage = user?.permissions.includes("settings.manage") ?? false;
  const canReadUsers = (user?.permissions.includes("users.read") ?? false) && (user?.permissions.includes("roles.read") ?? false);
  const canManageUsers = user?.permissions.includes("users.manage") ?? false;
  const isSystemAdmin = user?.roles.includes("system_admin") ?? false;
  const [tab, setTab] = useState<Tab>("print");
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [appearance, setAppearance] = useState(readAppearance);
  const [headerLogo, setHeaderLogo] = useState(readHeaderLogo);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [userUsername, setUserUsername] = useState("");
  const [userDisplayName, setUserDisplayName] = useState("");
  const [userPassword, setUserPassword] = useState("");
  const [userRole, setUserRole] = useState("operations_manager");
  const [userActive, setUserActive] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [companySettings, userRows, roleRows] = await Promise.all([
        api<CompanySettings>("/master-data/settings"),
        canReadUsers ? api<AuthUser[]>("/identity/users") : Promise.resolve([]),
        canReadUsers ? api<Role[]>("/identity/roles") : Promise.resolve([]),
      ]);
      setSettings(companySettings);
      setUsers(userRows);
      setRoles(roleRows);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل الإعدادات");
    } finally {
      setLoading(false);
    }
  }, [canReadUsers]);

  useEffect(() => { void load(); }, [load]);

  async function savePrintSettings(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setError(""); setNotice("");
    try {
      setSettings(await api<CompanySettings>("/master-data/settings", { method: "PUT", body: JSON.stringify(settings) }));
      setNotice("تم حفظ بيانات فاتورة المبيعات.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر حفظ بيانات فاتورة المبيعات");
    }
  }

  function saveAppearance(event: FormEvent) {
    event.preventDefault();
    applyAppearance(appearance);
    setNotice("تم حفظ وتطبيق إعدادات المظهر على هذا الجهاز.");
  }

  function saveHeaderLogo(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem(headerLogoKey, JSON.stringify(headerLogo));
    window.dispatchEvent(new Event("pipeerp-header-logo-change"));
    setNotice("تم حفظ وتطبيق شعار الهيدر.");
  }

  function chooseHeaderLogo(file: File | undefined) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("ملف الشعار يجب أن يكون صورة.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () =>
      setHeaderLogo({ image: typeof reader.result === "string" ? reader.result : "" });
    reader.readAsDataURL(file);
  }

  async function resetSystem(event: FormEvent) {
    event.preventDefault();
    if (!window.confirm("سيتم حذف كل الحركات مع الاحتفاظ بالبيانات الأساسية. هل تريد الاستمرار؟")) return;
    setError(""); setNotice("");
    try {
      await api("/system/reset", { method: "POST", body: JSON.stringify({ password: resetPassword, confirmation: resetConfirmation }) });
      setResetPassword(""); setResetConfirmation("");
      setNotice("تم حذف كل الحركات مع الاحتفاظ بالبيانات الأساسية.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تصفير الحركات");
    }
  }

  function clearUserForm() {
    setSelectedUserId(null);
    setUserUsername("");
    setUserDisplayName("");
    setUserPassword("");
    setUserRole(roles[0]?.code ?? "operations_manager");
    setUserActive(true);
  }

  function selectUser(item: AuthUser) {
    setSelectedUserId(item.id);
    setUserUsername(item.username);
    setUserDisplayName(item.display_name);
    setUserPassword("");
    setUserRole(item.roles[0] ?? roles[0]?.code ?? "operations_manager");
    setUserActive(item.is_active);
  }

  async function saveUser(event: FormEvent) {
    event.preventDefault();
    setError(""); setNotice("");
    try {
      if (selectedUserId) {
        const editingCurrentUser = selectedUserId === user?.id;
        await api<AuthUser>(`/identity/users/${selectedUserId}`, {
          method: "PATCH",
          body: JSON.stringify({
            display_name: userDisplayName,
            ...(!editingCurrentUser ? { is_active: userActive, role_codes: userRole ? [userRole] : [] } : {}),
            ...(userPassword ? { new_password: userPassword, must_change_password: false } : {}),
          }),
        });
        setNotice("تم حفظ المستخدم والصلاحيات.");
      } else {
        await api<AuthUser>("/identity/users", {
          method: "POST",
          body: JSON.stringify({
            username: userUsername,
            display_name: userDisplayName,
            password: userPassword,
            role_codes: userRole ? [userRole] : [],
            must_change_password: false,
          }),
        });
        setNotice("تم إنشاء المستخدم.");
      }
      clearUserForm();
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر حفظ المستخدم");
    }
  }

  async function removeSelectedUser() {
    if (!selectedUserId || selectedUserId === user?.id) return;
    if (!window.confirm("هل تريد حذف المستخدم المحدد؟")) return;
    setError(""); setNotice("");
    try {
      await api(`/identity/users/${selectedUserId}`, { method: "DELETE" });
      clearUserForm();
      setNotice("تم حذف المستخدم.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر حذف المستخدم");
    }
  }

  const canManageSystem = isSystemAdmin && canManage;
  return <AppShell>
    <section className="page-heading"><div><h2>الإعدادات</h2><p>إدارة المستخدمين والصلاحيات وتصفير حركات النظام.</p></div><button type="button" className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17}/> تحديث</button></section>
    {error ? <div className="alert alert--error">{error}</div> : null}
    {notice ? <div className="alert alert--success"><Check size={17}/> {notice}</div> : null}
    <SettingsTabs tab={tab} canManage={canManage} canReadUsers={canReadUsers} isSystemAdmin={isSystemAdmin} onSelect={setTab}/>
    {tab === "print" && settings ? <PrintSettingsPanel settings={settings} canManage={canManage} onChange={setSettings} onSubmit={(event) => void savePrintSettings(event)}/> : null}
    {tab === "watermark" ? <HeaderLogoPanel headerLogo={headerLogo} onChoose={chooseHeaderLogo} onClear={() => setHeaderLogo({ image: "" })} onSubmit={saveHeaderLogo}/> : null}
    {tab === "appearance" ? <AppearancePanel appearance={appearance} onChange={setAppearance} onSubmit={saveAppearance}/> : null}
    {tab === "backup" && canManageSystem ? <BackupPanel/> : null}
    {tab === "users" && canReadUsers ? <UsersPanel
      currentUserId={user?.id}
      canManageUsers={canManageUsers}
      users={users}
      roles={roles}
      selectedUserId={selectedUserId}
      username={userUsername}
      displayName={userDisplayName}
      password={userPassword}
      role={userRole}
      active={userActive}
      onSelectUser={selectUser}
      onUsernameChange={setUserUsername}
      onDisplayNameChange={setUserDisplayName}
      onPasswordChange={setUserPassword}
      onRoleChange={setUserRole}
      onActiveChange={setUserActive}
      onClear={clearUserForm}
      onRemove={() => void removeSelectedUser()}
      onSubmit={(event) => void saveUser(event)}
    /> : null}
    {tab === "reset" && canManageSystem ? <ResetPanel
      confirmation={resetConfirmation}
      password={resetPassword}
      onConfirmationChange={setResetConfirmation}
      onPasswordChange={setResetPassword}
      onSubmit={(event) => void resetSystem(event)}
    /> : null}
  </AppShell>;
}
