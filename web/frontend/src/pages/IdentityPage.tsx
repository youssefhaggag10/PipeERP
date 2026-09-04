import { Check, Plus, RefreshCw, Shield, UserRoundCheck, UserRoundX, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";

import { type AuthUser, useAuth } from "../auth/AuthContext";
import { permissionLabels, type Permission } from "../auth/permissions";
import { AppShell } from "../components/AppShell";
import { api, ApiError } from "../lib/api";

type Role = {
  id: string;
  code: string;
  name_ar: string;
  description: string;
  is_system: boolean;
  permissions: Permission[];
};

type AuditEntry = {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  outcome: string;
  created_at: string;
};

const allPermissions = Object.keys(permissionLabels) as Permission[];

export function IdentityPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [selectedRole, setSelectedRole] = useState("operations_manager");
  const [roleCode, setRoleCode] = useState("");
  const [roleName, setRoleName] = useState("");
  const [rolePermissions, setRolePermissions] = useState<Set<Permission>>(new Set());

  const canRead = user?.permissions.includes("users.read") && user.permissions.includes("roles.read");
  const canManageUsers = user?.permissions.includes("users.manage") ?? false;
  const canManageRoles = user?.permissions.includes("roles.manage") ?? false;
  const canReadAudit = user?.permissions.includes("audit.read") ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userRows, roleRows, auditRows] = await Promise.all([
        api<AuthUser[]>("/identity/users"),
        api<Role[]>("/identity/roles"),
        canReadAudit
          ? api<AuditEntry[]>("/identity/audit?limit=20")
          : Promise.resolve([]),
      ]);
      setUsers(userRows);
      setRoles(roleRows);
      setAudit(auditRows);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحميل بيانات الصلاحيات");
    } finally {
      setLoading(false);
    }
  }, [canReadAudit]);

  useEffect(() => {
    if (canRead) void load();
  }, [canRead, load]);

  const activeUsers = useMemo(() => users.filter((item) => item.is_active).length, [users]);

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api<AuthUser>("/identity/users", {
        method: "POST",
        body: JSON.stringify({
          username,
          display_name: displayName,
          password,
          role_codes: [selectedRole],
          must_change_password: true,
        }),
      });
      setUsername("");
      setDisplayName("");
      setPassword("");
      setNotice("تم إنشاء المستخدم وسيُطلب منه تغيير كلمة المرور عند أول دخول.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء المستخدم");
    }
  }

  async function toggleUser(item: AuthUser) {
    setError("");
    try {
      await api<AuthUser>(`/identity/users/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !item.is_active }),
      });
      setNotice(item.is_active ? "تم تعطيل الحساب وإبطال جلساته." : "تم تفعيل الحساب.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تعديل المستخدم");
    }
  }

  function togglePermission(permission: Permission) {
    setRolePermissions((current) => {
      const updated = new Set(current);
      if (updated.has(permission)) updated.delete(permission);
      else updated.add(permission);
      return updated;
    });
  }

  async function createCustomRole(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api<Role>("/identity/roles", {
        method: "POST",
        body: JSON.stringify({
          code: roleCode,
          name_ar: roleName,
          permissions: [...rolePermissions],
        }),
      });
      setRoleCode("");
      setRoleName("");
      setRolePermissions(new Set());
      setNotice("تم إنشاء الدور المخصص.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر إنشاء الدور");
    }
  }

  async function toggleExistingPermission(role: Role, permission: Permission) {
    const permissions = new Set(role.permissions);
    if (permissions.has(permission)) permissions.delete(permission);
    else permissions.add(permission);
    setError("");
    try {
      await api<Role>(`/identity/roles/${role.id}/permissions`, {
        method: "PUT",
        body: JSON.stringify({ permissions: [...permissions] }),
      });
      setNotice("تم تحديث صلاحيات الدور وإبطال جلسات المستخدمين المتأثرين.");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "تعذر تحديث الدور");
    }
  }

  if (!canRead) return <Navigate to="/" replace />;

  return (
    <AppShell>
      <section className="page-heading">
        <div><span className="eyebrow">الأمان والتحكم</span><h2>المستخدمون والأدوار</h2><p>صلاحيات واضحة ومفروضة من الخادم، مع إبطال فوري للجلسات عند التغيير.</p></div>
        <button className="secondary-button" onClick={() => void load()} disabled={loading}><RefreshCw size={17} /> تحديث</button>
      </section>

      {error ? <div className="alert alert--error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert--success"><Check size={17} />{notice}</div> : null}

      <section className="identity-stats">
        <article><Users size={20} /><span>إجمالي المستخدمين</span><strong>{users.length}</strong></article>
        <article><UserRoundCheck size={20} /><span>حسابات نشطة</span><strong>{activeUsers}</strong></article>
        <article><Shield size={20} /><span>الأدوار المتاحة</span><strong>{roles.length}</strong></article>
      </section>

      <section className="identity-layout">
        <article className="panel identity-panel">
          <header className="panel__head"><div><h3>الحسابات</h3><p>التعطيل يبطل كل جلسات المستخدم فورًا</p></div></header>
          <div className="user-list">
            {users.map((item) => (
              <div className="user-row" key={item.id}>
                <span className="profile-chip__avatar">{item.display_name.charAt(0)}</span>
                <span><strong>{item.display_name}</strong><small>@{item.username} · {item.roles.join("، ")}</small></span>
                <span className={`status-badge ${item.is_active ? "status-badge--active" : ""}`}>{item.is_active ? "نشط" : "معطل"}</span>
                {canManageUsers ? <button className="icon-button" aria-label={item.is_active ? "تعطيل المستخدم" : "تفعيل المستخدم"} onClick={() => void toggleUser(item)}>{item.is_active ? <UserRoundX size={18} /> : <UserRoundCheck size={18} />}</button> : null}
              </div>
            ))}
          </div>
        </article>

        {canManageUsers ? <article className="panel identity-form-card"><header className="panel__head"><div><h3>مستخدم جديد</h3><p>لا يوجد تسجيل عام للنظام</p></div></header><form className="compact-form" onSubmit={createUser}><label>الاسم الظاهر<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required minLength={2} /></label><label>اسم المستخدم<input value={username} onChange={(event) => setUsername(event.target.value)} required /></label><label>كلمة مرور مؤقتة<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} /></label><label>الدور<select value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>{roles.map((role) => <option value={role.code} key={role.id}>{role.name_ar}</option>)}</select></label><button className="primary-button"><Plus size={17} /> إنشاء الحساب</button></form></article> : null}
      </section>

      <section className="role-grid">
        {roles.map((role) => <article className="role-card" key={role.id}><header><span className="role-card__icon"><Shield size={19} /></span><div><strong>{role.name_ar}</strong><small>{role.code}</small></div>{role.is_system ? <span className="status-badge status-badge--system">أساسي</span> : null}</header>{canManageRoles && !role.is_system ? <div className="role-permission-list">{allPermissions.map((permission) => <label className="check-field" key={permission}><input type="checkbox" checked={role.permissions.includes(permission)} onChange={() => void toggleExistingPermission(role, permission)} /><span>{permissionLabels[permission]}</span></label>)}</div> : <div className="permission-chips">{role.permissions.map((permission) => <span key={permission}>{permissionLabels[permission]}</span>)}</div>}</article>)}
      </section>

      {canManageRoles ? <section className="panel custom-role"><header className="panel__head"><div><h3>إنشاء دور مخصص</h3><p>الأدوار الأساسية ثابتة للحفاظ على سلامة النظام</p></div></header><form className="custom-role__form" onSubmit={createCustomRole}><label>رمز الدور<input dir="ltr" pattern="[a-z][a-z0-9_]{2,79}" value={roleCode} onChange={(event) => setRoleCode(event.target.value)} placeholder="warehouse_viewer" required /></label><label>اسم الدور<input value={roleName} onChange={(event) => setRoleName(event.target.value)} required /></label><fieldset><legend>الصلاحيات</legend>{allPermissions.map((permission) => <label className="check-field" key={permission}><input type="checkbox" checked={rolePermissions.has(permission)} onChange={() => togglePermission(permission)} /><span>{permissionLabels[permission]}</span></label>)}</fieldset><button className="primary-button"><Plus size={17} /> إنشاء الدور</button></form></section> : null}

      {audit.length ? <section className="panel audit-panel"><header className="panel__head"><div><h3>آخر أحداث التدقيق</h3><p>محاولات الدخول وتغييرات الهوية والصلاحيات</p></div></header><div className="audit-list">{audit.map((entry) => <div key={entry.id}><span className={`audit-outcome audit-outcome--${entry.outcome}`} /> <strong>{entry.event_type}</strong><small>{new Intl.DateTimeFormat("ar-EG", { dateStyle: "medium", timeStyle: "short" }).format(new Date(entry.created_at))}</small></div>)}</div></section> : null}
    </AppShell>
  );
}
