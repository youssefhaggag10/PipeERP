from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.database.connection import Database
from app.models.user import User

EGYPT_TZ = ZoneInfo("Africa/Cairo")

CRM_SQL = """
CREATE TABLE IF NOT EXISTS crm_sources(
 code TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, sequence INTEGER NOT NULL DEFAULT 100
);
CREATE TABLE IF NOT EXISTS crm_stages(
 code TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, sequence INTEGER NOT NULL,
 is_won INTEGER NOT NULL DEFAULT 0, is_lost INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS crm_leads(
 id INTEGER PRIMARY KEY AUTOINCREMENT, lead_number TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL, phone TEXT NOT NULL, alternate_phone TEXT, company TEXT,
 address TEXT, source_code TEXT REFERENCES crm_sources(code),
 customer_type TEXT NOT NULL DEFAULT 'potential', temperature TEXT NOT NULL DEFAULT 'warm',
 stage_code TEXT NOT NULL DEFAULT 'new' REFERENCES crm_stages(code),
 assigned_user_id INTEGER REFERENCES users(id), interested_products TEXT, tags TEXT,
 opportunity_value REAL NOT NULL DEFAULT 0, general_notes TEXT, lost_reason TEXT,
 customer_partner_id INTEGER REFERENCES partners(id), created_by INTEGER REFERENCES users(id),
 last_contact_at TEXT, is_active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS crm_activities(
 id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL REFERENCES crm_leads(id),
 activity_type TEXT NOT NULL, subject TEXT NOT NULL, notes TEXT, due_at TEXT,
 priority TEXT NOT NULL DEFAULT 'normal', assigned_user_id INTEGER REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'scheduled', outcome TEXT, created_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_crm_leads_stage ON crm_leads(stage_code,is_active);
CREATE INDEX IF NOT EXISTS idx_crm_leads_owner ON crm_leads(assigned_user_id,is_active);
CREATE INDEX IF NOT EXISTS idx_crm_activities_due ON crm_activities(status,due_at);
CREATE INDEX IF NOT EXISTS idx_crm_activities_lead ON crm_activities(lead_id,id);
"""

SOURCES = (
    ("facebook", "فيسبوك", 10),
    ("instagram", "إنستجرام", 20),
    ("whatsapp", "واتساب", 30),
    ("website", "الموقع", 40),
    ("paid_ad", "إعلان ممول", 50),
    ("referral", "ترشيح عميل", 60),
    ("sales_rep", "مندوب", 70),
    ("inbound_call", "اتصال وارد", 80),
    ("exhibition", "معرض", 90),
    ("other", "مصدر آخر", 100),
)
STAGES = (
    ("new", "عميل جديد", 10, 0, 0),
    ("not_contacted", "لم يتم التواصل", 20, 0, 0),
    ("contacted", "تم التواصل", 30, 0, 0),
    ("interested", "مهتم", 40, 0, 0),
    ("quotation", "إرسال عرض سعر", 50, 0, 0),
    ("negotiation", "تفاوض", 60, 0, 0),
    ("waiting", "انتظار قرار", 70, 0, 0),
    ("won", "تم البيع", 80, 1, 0),
    ("postponed", "مؤجل", 90, 0, 0),
    ("no_answer", "لا يرد", 100, 0, 0),
    ("not_interested", "غير مهتم", 110, 0, 1),
    ("invalid_phone", "رقم غير صحيح", 120, 0, 1),
    ("lost", "خسارة الصفقة", 130, 0, 1),
)


class CRMRepository:
    def __init__(self, database: Database, current_user: User) -> None:
        self.database = database
        self.current_user = current_user
        self.is_manager = current_user.role.lower() in {"admin", "manager", "owner", "supervisor"}
        with database.session(immediate=True) as con:
            con.executescript(CRM_SQL)
            con.executemany("INSERT OR IGNORE INTO crm_sources VALUES(?,?,?)", SOURCES)
            con.executemany("INSERT OR IGNORE INTO crm_stages VALUES(?,?,?,?,?)", STAGES)

    def _scope(self, alias: str = "l") -> tuple[str, tuple]:
        return (
            ("1=1", ())
            if self.is_manager
            else (f"{alias}.assigned_user_id=?", (self.current_user.id,))
        )

    @staticmethod
    def _utc(local_text: str) -> str:
        value = datetime.fromisoformat(local_text)
        if value.tzinfo is None:
            value = value.replace(tzinfo=EGYPT_TZ)
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def list_sources(self) -> list[dict]:
        return [
            dict(x)
            for x in self.database.fetch_all("SELECT code,name FROM crm_sources ORDER BY sequence")
        ]

    def list_stages(self) -> list[dict]:
        return [
            dict(x) for x in self.database.fetch_all("SELECT * FROM crm_stages ORDER BY sequence")
        ]

    def list_users(self) -> list[dict]:
        if not self.is_manager:
            return [{"id": self.current_user.id, "full_name": self.current_user.display_name}]
        return [
            dict(x)
            for x in self.database.fetch_all(
                "SELECT id,full_name FROM users WHERE is_active=1 ORDER BY full_name"
            )
        ]

    def summary(self) -> dict:
        scope, params = self._scope()
        lead = self.database.fetch_one(
            f"""
            SELECT COUNT(*) total,
             SUM(CASE WHEN stage_code='new' THEN 1 ELSE 0 END) new_count,
             SUM(CASE WHEN temperature='hot' AND stage_code NOT IN('won','lost','not_interested','invalid_phone') THEN 1 ELSE 0 END) hot_count,
             SUM(CASE WHEN stage_code='won' THEN 1 ELSE 0 END) won_count,
             COALESCE(SUM(CASE WHEN stage_code NOT IN('won','lost','not_interested','invalid_phone') THEN opportunity_value ELSE 0 END),0) open_value
            FROM crm_leads l WHERE is_active=1 AND {scope}
        """,
            params,
        )
        activity_scope = "1=1" if self.is_manager else "assigned_user_id=?"
        activity_params = () if self.is_manager else (self.current_user.id,)
        act = self.database.fetch_one(
            f"""
            SELECT SUM(CASE WHEN status='scheduled' AND date(due_at)=date('now') THEN 1 ELSE 0 END) today_count,
                   SUM(CASE WHEN status='scheduled' AND due_at<CURRENT_TIMESTAMP THEN 1 ELSE 0 END) overdue_count
            FROM crm_activities WHERE {activity_scope}
        """,
            activity_params,
        )
        result = dict(lead or {})
        result.update(dict(act or {}))
        return {k: v or 0 for k, v in result.items()}

    def list_leads(
        self, search: str = "", stage: str | None = None, owner: int | None = None
    ) -> list[dict]:
        scope, scope_params = self._scope()
        where = ["l.is_active=1", scope]
        params: list = list(scope_params)
        if search.strip():
            token = f"%{search.strip()}%"
            where.append(
                "(l.lead_number LIKE ? OR l.name LIKE ? OR l.phone LIKE ? OR COALESCE(l.company,'') LIKE ? OR COALESCE(l.tags,'') LIKE ?)"
            )
            params += [token] * 5
        if stage:
            where.append("l.stage_code=?")
            params.append(stage)
        if owner is not None and self.is_manager:
            where.append("l.assigned_user_id=?")
            params.append(owner)
        return [
            dict(x)
            for x in self.database.fetch_all(
                f"""
            SELECT l.*,s.name stage_name,src.name source_name,COALESCE(u.full_name,'') owner_name,
             (SELECT MIN(a.due_at) FROM crm_activities a WHERE a.lead_id=l.id AND a.status='scheduled') next_activity_at,
             (SELECT COUNT(*) FROM crm_activities a WHERE a.lead_id=l.id) activity_count
            FROM crm_leads l LEFT JOIN crm_stages s ON s.code=l.stage_code
            LEFT JOIN crm_sources src ON src.code=l.source_code LEFT JOIN users u ON u.id=l.assigned_user_id
            WHERE {" AND ".join(where)} ORDER BY CASE WHEN next_activity_at IS NULL THEN 1 ELSE 0 END,next_activity_at,l.id DESC
        """,
                params,
            )
        ]

    def get_lead(self, lead_id: int) -> dict:
        scope, params = self._scope()
        row = self.database.fetch_one(
            f"""
            SELECT l.*,s.name stage_name,src.name source_name,COALESCE(u.full_name,'') owner_name
            FROM crm_leads l LEFT JOIN crm_stages s ON s.code=l.stage_code
            LEFT JOIN crm_sources src ON src.code=l.source_code LEFT JOIN users u ON u.id=l.assigned_user_id
            WHERE l.id=? AND l.is_active=1 AND {scope}
        """,
            (lead_id, *params),
        )
        if row is None:
            raise ValueError("العميل المحتمل غير موجود أو غير مسموح لك بعرضه")
        return dict(row)

    def save_lead(self, data: dict, lead_id: int | None = None) -> int:
        name, phone = str(data.get("name", "")).strip(), str(data.get("phone", "")).strip()
        if not name or not phone:
            raise ValueError("اسم العميل ورقم الهاتف مطلوبان")
        owner = int(data.get("assigned_user_id") or self.current_user.id)
        if not self.is_manager:
            owner = self.current_user.id
        values = (
            name,
            phone,
            str(data.get("alternate_phone", "")).strip(),
            str(data.get("company", "")).strip(),
            str(data.get("address", "")).strip(),
            data.get("source_code") or "other",
            data.get("customer_type") or "potential",
            data.get("temperature") or "warm",
            data.get("stage_code") or "new",
            owner,
            str(data.get("interested_products", "")).strip(),
            str(data.get("tags", "")).strip(),
            float(data.get("opportunity_value") or 0),
            str(data.get("general_notes", "")).strip(),
            str(data.get("lost_reason", "")).strip(),
        )
        with self.database.session(immediate=True) as con:
            duplicate = con.execute(
                "SELECT id,name FROM crm_leads WHERE phone=? AND is_active=1 AND (? IS NULL OR id<>?)",
                (phone, lead_id, lead_id),
            ).fetchone()
            if duplicate:
                raise ValueError(f"رقم الهاتف مسجل بالفعل للعميل {duplicate['name']}")
            if lead_id is None:
                next_id = int(
                    con.execute("SELECT COALESCE(MAX(id),0)+1 n FROM crm_leads").fetchone()["n"]
                )
                number = f"LD{next_id:05d}"
                cur = con.execute(
                    """
                    INSERT INTO crm_leads(lead_number,name,phone,alternate_phone,company,address,source_code,customer_type,temperature,stage_code,assigned_user_id,interested_products,tags,opportunity_value,general_notes,lost_reason,created_by)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                    (number, *values, self.current_user.id),
                )
                lead_id = int(cur.lastrowid)
                con.execute(
                    "INSERT INTO crm_activities(lead_id,activity_type,subject,notes,assigned_user_id,status,created_by,completed_at) VALUES(?, 'note','إنشاء العميل المحتمل',? ,?,'done',?,CURRENT_TIMESTAMP)",
                    (lead_id, number, owner, self.current_user.id),
                )
            else:
                self.get_lead(lead_id)
                con.execute(
                    """
                    UPDATE crm_leads SET name=?,phone=?,alternate_phone=?,company=?,address=?,source_code=?,customer_type=?,temperature=?,stage_code=?,assigned_user_id=?,interested_products=?,tags=?,opportunity_value=?,general_notes=?,lost_reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?
                """,
                    (*values, lead_id),
                )
        return int(lead_id)

    def set_stage(self, lead_id: int, stage: str) -> None:
        lead = self.get_lead(lead_id)
        target = self.database.fetch_one("SELECT name FROM crm_stages WHERE code=?", (stage,))
        if not target:
            raise ValueError("مرحلة غير صحيحة")
        with self.database.session(immediate=True) as con:
            con.execute(
                "UPDATE crm_leads SET stage_code=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (stage, lead_id),
            )
            con.execute(
                "INSERT INTO crm_activities(lead_id,activity_type,subject,notes,assigned_user_id,status,created_by,completed_at) VALUES(?,'stage','تغيير المرحلة',?,?, 'done',?,CURRENT_TIMESTAMP)",
                (
                    lead_id,
                    f"من {lead['stage_name']} إلى {target['name']}",
                    lead.get("assigned_user_id"),
                    self.current_user.id,
                ),
            )

    def add_note(self, lead_id: int, note: str, kind: str = "note") -> None:
        lead = self.get_lead(lead_id)
        note = note.strip()
        if not note:
            raise ValueError("اكتب الملاحظة أولًا")
        with self.database.session(immediate=True) as con:
            con.execute(
                "INSERT INTO crm_activities(lead_id,activity_type,subject,notes,assigned_user_id,status,created_by,completed_at) VALUES(?,?, 'ملاحظة متابعة',?,?, 'done',?,CURRENT_TIMESTAMP)",
                (lead_id, kind, note, lead.get("assigned_user_id"), self.current_user.id),
            )
            con.execute(
                "UPDATE crm_leads SET last_contact_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (lead_id,),
            )

    def schedule(
        self,
        lead_id: int,
        kind: str,
        subject: str,
        notes: str,
        due_local: str,
        priority: str,
        owner: int | None,
    ) -> None:
        lead = self.get_lead(lead_id)
        if not subject.strip() or not due_local.strip():
            raise ValueError("عنوان وموعد النشاط مطلوبان")
        assigned = int(owner or lead.get("assigned_user_id") or self.current_user.id)
        if not self.is_manager:
            assigned = self.current_user.id
        self.database.execute(
            "INSERT INTO crm_activities(lead_id,activity_type,subject,notes,due_at,priority,assigned_user_id,status,created_by) VALUES(?,?,?,?,?,?,?,'scheduled',?)",
            (
                lead_id,
                kind,
                subject.strip(),
                notes.strip(),
                self._utc(due_local),
                priority,
                assigned,
                self.current_user.id,
            ),
        )

    def list_timeline(self, lead_id: int) -> list[dict]:
        self.get_lead(lead_id)
        return [
            dict(x)
            for x in self.database.fetch_all(
                """
            SELECT a.*,COALESCE(u.full_name,'') owner_name,COALESCE(c.full_name,'') creator_name
            FROM crm_activities a LEFT JOIN users u ON u.id=a.assigned_user_id LEFT JOIN users c ON c.id=a.created_by
            WHERE a.lead_id=? ORDER BY a.id DESC
        """,
                (lead_id,),
            )
        ]

    def list_activities(self, status: str | None = "scheduled") -> list[dict]:
        scope = "1=1" if self.is_manager else "a.assigned_user_id=?"
        params: list = [] if self.is_manager else [self.current_user.id]
        if status:
            scope += " AND a.status=?"
            params.append(status)
        return [
            dict(x)
            for x in self.database.fetch_all(
                f"""
            SELECT a.*,l.lead_number,l.name lead_name,l.phone,COALESCE(u.full_name,'') owner_name,
             CASE WHEN a.status='scheduled' AND a.due_at<CURRENT_TIMESTAMP THEN 'overdue' WHEN a.status='scheduled' AND date(a.due_at)=date('now') THEN 'today' ELSE a.status END display_status
            FROM crm_activities a JOIN crm_leads l ON l.id=a.lead_id LEFT JOIN users u ON u.id=a.assigned_user_id
            WHERE l.is_active=1 AND {scope} ORDER BY CASE WHEN a.due_at IS NULL THEN 1 ELSE 0 END,a.due_at,a.id DESC
        """,
                params,
            )
        ]

    def due_activities(self) -> list[dict]:
        scope = "1=1" if self.is_manager else "a.assigned_user_id=?"
        params = () if self.is_manager else (self.current_user.id,)
        return [
            dict(x)
            for x in self.database.fetch_all(
                f"""
            SELECT a.id,a.lead_id,a.subject,a.due_at,l.name lead_name,l.phone FROM crm_activities a
            JOIN crm_leads l ON l.id=a.lead_id WHERE a.status='scheduled' AND a.due_at<=datetime('now','+5 minutes') AND {scope}
            ORDER BY a.due_at LIMIT 20
        """,
                params,
            )
        ]

    def complete_activity(self, activity_id: int, outcome: str) -> None:
        row = self.database.fetch_one(
            "SELECT lead_id FROM crm_activities WHERE id=?", (activity_id,)
        )
        if not row:
            raise ValueError("النشاط غير موجود")
        with self.database.session(immediate=True) as con:
            con.execute(
                "UPDATE crm_activities SET status='done',outcome=?,completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (outcome.strip(), activity_id),
            )
            con.execute(
                "UPDATE crm_leads SET last_contact_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (row["lead_id"],),
            )

    def reschedule(self, activity_id: int, due_local: str) -> None:
        self.database.execute(
            "UPDATE crm_activities SET status='scheduled',due_at=?,completed_at=NULL,outcome=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (self._utc(due_local), activity_id),
        )

    def cancel_activity(self, activity_id: int) -> None:
        self.database.execute(
            "UPDATE crm_activities SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (activity_id,),
        )

    def convert_to_customer(self, lead_id: int) -> int:
        lead = self.get_lead(lead_id)
        if lead.get("customer_partner_id"):
            return int(lead["customer_partner_id"])
        with self.database.session(immediate=True) as con:
            existing = con.execute(
                "SELECT id FROM partners WHERE partner_type='customer' AND phone=? AND is_active=1 LIMIT 1",
                (lead["phone"],),
            ).fetchone()
            if existing:
                partner_id = int(existing["id"])
            else:
                next_id = int(
                    con.execute("SELECT COALESCE(MAX(id),0)+1 n FROM partners").fetchone()["n"]
                )
                cur = con.execute(
                    "INSERT INTO partners(partner_type,code,name,phone,address) VALUES('customer',?,?,?,?)",
                    (f"CRM-C{next_id:05d}", lead["name"], lead["phone"], lead.get("address", "")),
                )
                partner_id = int(cur.lastrowid)
            con.execute(
                "UPDATE crm_leads SET customer_partner_id=?,stage_code='won',customer_type='customer',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (partner_id, lead_id),
            )
            con.execute(
                "INSERT INTO crm_activities(lead_id,activity_type,subject,notes,assigned_user_id,status,created_by,completed_at) VALUES(?,'conversion','تحويل إلى عميل',?,?, 'done',?,CURRENT_TIMESTAMP)",
                (
                    lead_id,
                    f"تم ربط العميل برقم {partner_id}",
                    lead.get("assigned_user_id"),
                    self.current_user.id,
                ),
            )
            return partner_id

    def pipeline(self) -> list[dict]:
        scope, params = self._scope()
        return [
            dict(x)
            for x in self.database.fetch_all(
                f"""
            SELECT s.code,s.name,s.sequence,COUNT(l.id) lead_count,COALESCE(SUM(l.opportunity_value),0) total_value
            FROM crm_stages s LEFT JOIN crm_leads l ON l.stage_code=s.code AND l.is_active=1 AND {scope}
            GROUP BY s.code,s.name,s.sequence ORDER BY s.sequence
        """,
                params,
            )
        ]

    def reports(self, mode: str) -> list[dict]:
        scope, params = self._scope()
        if mode == "source":
            sql = f"SELECT COALESCE(src.name,'غير محدد') label,COUNT(l.id) total,SUM(CASE WHEN l.stage_code='won' THEN 1 ELSE 0 END) won,COALESCE(SUM(l.opportunity_value),0) value FROM crm_leads l LEFT JOIN crm_sources src ON src.code=l.source_code WHERE l.is_active=1 AND {scope} GROUP BY label ORDER BY total DESC"
        elif mode == "owner":
            sql = f"SELECT COALESCE(u.full_name,'غير مسند') label,COUNT(l.id) total,SUM(CASE WHEN l.stage_code='won' THEN 1 ELSE 0 END) won,COALESCE(SUM(l.opportunity_value),0) value FROM crm_leads l LEFT JOIN users u ON u.id=l.assigned_user_id WHERE l.is_active=1 AND {scope} GROUP BY label ORDER BY won DESC,total DESC"
        else:
            sql = f"SELECT CASE WHEN TRIM(COALESCE(l.lost_reason,''))='' THEN 'غير محدد' ELSE l.lost_reason END label,COUNT(*) total,0 won,0 value FROM crm_leads l JOIN crm_stages s ON s.code=l.stage_code AND s.is_lost=1 WHERE l.is_active=1 AND {scope} GROUP BY label ORDER BY total DESC"
        return [dict(x) for x in self.database.fetch_all(sql, params)]
