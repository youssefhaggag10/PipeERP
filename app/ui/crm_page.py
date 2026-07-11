from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget, QInputDialog,
)

from app.repositories.crm_repository import CRMRepository
from app.utils.datetime_utils import format_egypt_datetime

CUSTOMER_TYPES = {"potential":"عميل محتمل","new":"عميل جديد","customer":"عميل حالي","vip":"VIP","follow_up":"يحتاج متابعة","not_interested":"غير مهتم"}
TEMPERATURES = {"cold":"بارد","warm":"دافئ","hot":"ساخن"}
ACTIVITY_TYPES = {"call":"مكالمة","whatsapp":"واتساب","message":"رسالة","meeting":"اجتماع","visit":"زيارة","email":"بريد","task":"مهمة"}
PRIORITIES = {"low":"منخفضة","normal":"عادية","high":"عالية","urgent":"عاجلة"}
STATUS = {"scheduled":"مجدول","today":"اليوم","overdue":"متأخر","done":"تم","cancelled":"ملغي"}


def fill_combo(combo: QComboBox, items: dict[str, str]) -> None:
    for code, label in items.items(): combo.addItem(label, code)


class LeadDialog(QDialog):
    def __init__(self, repo: CRMRepository, lead: dict | None = None, parent=None) -> None:
        super().__init__(parent); self.repo = repo; self.lead = lead or {}
        self.setWindowTitle("إضافة عميل محتمل" if not lead else "تعديل العميل المحتمل")
        self.resize(620, 700); self.setLayoutDirection(Qt.RightToLeft)
        self.name = QLineEdit(str(self.lead.get("name", "")))
        self.phone = QLineEdit(str(self.lead.get("phone", "")))
        self.alt = QLineEdit(str(self.lead.get("alternate_phone", "")))
        self.company = QLineEdit(str(self.lead.get("company", "")))
        self.address = QLineEdit(str(self.lead.get("address", "")))
        self.source = QComboBox()
        for x in repo.list_sources(): self.source.addItem(x["name"], x["code"])
        self.customer_type = QComboBox(); fill_combo(self.customer_type, CUSTOMER_TYPES)
        self.temperature = QComboBox(); fill_combo(self.temperature, TEMPERATURES)
        self.stage = QComboBox()
        for x in repo.list_stages(): self.stage.addItem(x["name"], x["code"])
        self.owner = QComboBox()
        for x in repo.list_users(): self.owner.addItem(x["full_name"], x["id"])
        self.products = QLineEdit(str(self.lead.get("interested_products", "")))
        self.tags = QLineEdit(str(self.lead.get("tags", "")))
        self.value = QLineEdit(str(self.lead.get("opportunity_value", 0) or 0))
        self.lost_reason = QLineEdit(str(self.lead.get("lost_reason", "")))
        self.notes = QTextEdit(str(self.lead.get("general_notes", "")))
        for combo, key in ((self.source,"source_code"),(self.customer_type,"customer_type"),(self.temperature,"temperature"),(self.stage,"stage_code"),(self.owner,"assigned_user_id")):
            i = combo.findData(self.lead.get(key));
            if i >= 0: combo.setCurrentIndex(i)
        form = QFormLayout()
        for label, widget in (("اسم العميل*",self.name),("الهاتف*",self.phone),("هاتف بديل",self.alt),("الشركة / النشاط",self.company),("العنوان",self.address),("المصدر",self.source),("نوع العميل",self.customer_type),("درجة الاهتمام",self.temperature),("مرحلة المبيعات",self.stage),("الموظف المسؤول",self.owner),("المنتجات المهتم بها",self.products),("Tags",self.tags),("قيمة الفرصة",self.value),("سبب الخسارة",self.lost_reason),("ملاحظات عامة",self.notes)): form.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addWidget(buttons)

    def payload(self) -> dict:
        try: value = float(self.value.text().strip() or 0)
        except ValueError as exc: raise ValueError("قيمة الفرصة يجب أن تكون رقمًا") from exc
        return {"name":self.name.text(),"phone":self.phone.text(),"alternate_phone":self.alt.text(),"company":self.company.text(),"address":self.address.text(),"source_code":self.source.currentData(),"customer_type":self.customer_type.currentData(),"temperature":self.temperature.currentData(),"stage_code":self.stage.currentData(),"assigned_user_id":self.owner.currentData(),"interested_products":self.products.text(),"tags":self.tags.text(),"opportunity_value":value,"general_notes":self.notes.toPlainText(),"lost_reason":self.lost_reason.text()}


class ActivityDialog(QDialog):
    def __init__(self, repo: CRMRepository, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("جدولة نشاط"); self.setLayoutDirection(Qt.RightToLeft)
        self.kind = QComboBox(); fill_combo(self.kind, ACTIVITY_TYPES)
        self.subject = QLineEdit("متابعة العميل")
        self.due = QDateTimeEdit(datetime.now() + timedelta(days=1)); self.due.setCalendarPopup(True); self.due.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.priority = QComboBox(); fill_combo(self.priority, PRIORITIES)
        self.owner = QComboBox()
        for x in repo.list_users(): self.owner.addItem(x["full_name"], x["id"])
        self.notes = QTextEdit()
        form = QFormLayout()
        for label, widget in (("نوع النشاط",self.kind),("العنوان",self.subject),("الموعد",self.due),("الأولوية",self.priority),("المسؤول",self.owner),("التفاصيل",self.notes)): form.addRow(label, widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self); layout.addLayout(form); layout.addWidget(buttons)


class CRMPage(QWidget):
    def __init__(self, repo: CRMRepository) -> None:
        super().__init__(); self.repo = repo; self.leads = []; self.activities = []; self.alerted = set()
        self.setLayoutDirection(Qt.RightToLeft)
        title = QLabel("CRM - متابعة العملاء"); title.setObjectName("titleLabel")
        subtitle = QLabel("العملاء المحتملون، دورة المبيعات، الأنشطة المجدولة والتذكيرات"); subtitle.setObjectName("subtitleLabel")
        self.tabs = QTabWidget(); self.tabs.addTab(self._dashboard(), "لوحة المتابعة"); self.tabs.addTab(self._leads(), "العملاء المحتملون"); self.tabs.addTab(self._activities(), "الأنشطة"); self.tabs.addTab(self._pipeline(), "مراحل المبيعات"); self.tabs.addTab(self._reports(), "تقارير CRM")
        layout = QVBoxLayout(self); layout.setContentsMargins(24,24,24,24); layout.addWidget(title); layout.addWidget(subtitle); layout.addWidget(self.tabs)
        self.timer = QTimer(self); self.timer.setInterval(60000); self.timer.timeout.connect(self._reminders); self.timer.start(); self.reload()

    def _metric(self, title: str):
        box = QGroupBox(title); value = QLabel("0"); value.setAlignment(Qt.AlignCenter); value.setStyleSheet("font-size:24px;font-weight:900;color:#38BDF8;")
        lay = QVBoxLayout(box); lay.addWidget(value); return box, value

    def _dashboard(self):
        page = QWidget(); grid = QGridLayout(); self.metrics = {}
        labels = [("total","إجمالي العملاء المحتملين"),("new_count","عملاء جدد"),("hot_count","عملاء ساخنون"),("today_count","أنشطة اليوم"),("overdue_count","أنشطة متأخرة"),("won_count","تم البيع"),("open_value","قيمة الفرص المفتوحة")]
        for i,(key,label) in enumerate(labels): self.metrics[key]=self._metric(label); grid.addWidget(self.metrics[key][0],i//3,i%3)
        self.due_table = QTableWidget(0,5); self.due_table.setHorizontalHeaderLabels(["الموعد","العميل","الهاتف","النشاط","الحالة"]); self._setup_table(self.due_table)
        lay = QVBoxLayout(page); lay.addLayout(grid); lay.addWidget(QLabel("المتابعات القريبة والمتأخرة")); lay.addWidget(self.due_table); return page

    def _leads(self):
        page = QWidget(); self.search = QLineEdit(); self.search.setPlaceholderText("بحث بالاسم أو الهاتف أو الكود أو الشركة أو Tag")
        self.stage_filter = QComboBox(); self.stage_filter.addItem("كل المراحل",None)
        for x in self.repo.list_stages(): self.stage_filter.addItem(x["name"],x["code"])
        self.owner_filter = QComboBox(); self.owner_filter.addItem("كل الموظفين",None)
        for x in self.repo.list_users(): self.owner_filter.addItem(x["full_name"],x["id"])
        self.search.textChanged.connect(self.reload_leads); self.stage_filter.currentIndexChanged.connect(self.reload_leads); self.owner_filter.currentIndexChanged.connect(self.reload_leads)
        filters = QHBoxLayout(); filters.addWidget(self.search); filters.addWidget(self.stage_filter); filters.addWidget(self.owner_filter)
        actions = QHBoxLayout()
        for text,fn in (("إضافة عميل محتمل",self.add_lead),("تعديل",self.edit_lead),("تغيير المرحلة",self.change_stage),("إضافة ملاحظة",self.add_note),("جدولة نشاط",self.schedule_activity),("تحويل إلى عميل",self.convert_customer),("سجل العميل",self.timeline),("تحديث",self.reload)):
            b=QPushButton(text); b.clicked.connect(fn); actions.addWidget(b)
        self.leads_table = QTableWidget(0,12); self.leads_table.setHorizontalHeaderLabels(["الكود","الاسم","الهاتف","المصدر","النوع","الاهتمام","المرحلة","المسؤول","قيمة الفرصة","المتابعة القادمة","الأنشطة","الحالة"]); self._setup_table(self.leads_table)
        self.leads_table.itemDoubleClicked.connect(lambda _: self.timeline())
        lay=QVBoxLayout(page); lay.addLayout(filters); lay.addLayout(actions); lay.addWidget(self.leads_table); return page

    def _activities(self):
        page=QWidget(); self.activity_status=QComboBox()
        for label,data in (("المجدولة","scheduled"),("المنفذة","done"),("الملغاة","cancelled"),("الكل",None)): self.activity_status.addItem(label,data)
        self.activity_status.currentIndexChanged.connect(self.reload_activities)
        actions=QHBoxLayout(); actions.addWidget(self.activity_status)
        for text,fn in (("تم التنفيذ",self.complete_activity),("إعادة جدولة",self.reschedule_activity),("إلغاء النشاط",self.cancel_activity)):
            b=QPushButton(text); b.clicked.connect(fn); actions.addWidget(b)
        self.activity_table=QTableWidget(0,9); self.activity_table.setHorizontalHeaderLabels(["الموعد","العميل","الهاتف","النوع","العنوان","الأولوية","المسؤول","الحالة","النتيجة"]); self._setup_table(self.activity_table)
        lay=QVBoxLayout(page); lay.addLayout(actions); lay.addWidget(self.activity_table); return page

    def _pipeline(self):
        page=QWidget(); self.pipeline_table=QTableWidget(0,4); self.pipeline_table.setHorizontalHeaderLabels(["المرحلة","عدد العملاء","قيمة الفرص","الترتيب"]); self._setup_table(self.pipeline_table); lay=QVBoxLayout(page); lay.addWidget(self.pipeline_table); return page

    def _reports(self):
        page=QWidget(); self.report_mode=QComboBox(); self.report_mode.addItem("حسب المصدر","source"); self.report_mode.addItem("حسب الموظف","owner"); self.report_mode.addItem("أسباب الخسارة","lost"); self.report_mode.currentIndexChanged.connect(self.reload_reports)
        self.report_table=QTableWidget(0,4); self.report_table.setHorizontalHeaderLabels(["البند","الإجمالي","تم البيع","القيمة"]); self._setup_table(self.report_table); lay=QVBoxLayout(page); lay.addWidget(self.report_mode); lay.addWidget(self.report_table); return page

    @staticmethod
    def _setup_table(table):
        table.setSelectionBehavior(QTableWidget.SelectRows); table.setEditTriggers(QTableWidget.NoEditTriggers); table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def reload(self): self.reload_dashboard(); self.reload_leads(); self.reload_activities(); self.reload_pipeline(); self.reload_reports()

    def reload_dashboard(self):
        data=self.repo.summary()
        for key,metric in self.metrics.items(): metric[1].setText(f"{float(data.get(key,0)):,.2f}" if key=="open_value" else str(data.get(key,0)))
        rows=self.repo.list_activities("scheduled")[:20]; self.due_table.setRowCount(len(rows))
        for r,row in enumerate(rows): self._set_row(self.due_table,r,[format_egypt_datetime(row.get("due_at")),row["lead_name"],row["phone"],row["subject"],STATUS.get(row["display_status"],row["display_status"])])

    def reload_leads(self):
        self.leads=self.repo.list_leads(self.search.text(),self.stage_filter.currentData(),self.owner_filter.currentData()); self.leads_table.setRowCount(len(self.leads))
        for r,row in enumerate(self.leads):
            values=[row["lead_number"],row["name"],row["phone"],row.get("source_name",""),CUSTOMER_TYPES.get(row["customer_type"],row["customer_type"]),TEMPERATURES.get(row["temperature"],row["temperature"]),row.get("stage_name",""),row.get("owner_name",""),f"{float(row.get('opportunity_value',0)):,.2f}",format_egypt_datetime(row.get("next_activity_at")),row.get("activity_count",0),"عميل فعلي" if row.get("customer_partner_id") else "Lead"]
            self._set_row(self.leads_table,r,values)
            if row.get("temperature")=="hot": self.leads_table.item(r,5).setBackground(QColor("#DC2626")); self.leads_table.item(r,5).setForeground(QColor("white"))

    def reload_activities(self):
        self.activities=self.repo.list_activities(self.activity_status.currentData()); self.activity_table.setRowCount(len(self.activities))
        for r,row in enumerate(self.activities):
            values=[format_egypt_datetime(row.get("due_at")),row["lead_name"],row["phone"],ACTIVITY_TYPES.get(row["activity_type"],row["activity_type"]),row["subject"],PRIORITIES.get(row["priority"],row["priority"]),row.get("owner_name",""),STATUS.get(row["display_status"],row["display_status"]),row.get("outcome","")]
            self._set_row(self.activity_table,r,values)
            if row["display_status"]=="overdue": self.activity_table.item(r,7).setBackground(QColor("#DC2626")); self.activity_table.item(r,7).setForeground(QColor("white"))

    def reload_pipeline(self):
        rows=self.repo.pipeline(); self.pipeline_table.setRowCount(len(rows))
        for r,row in enumerate(rows): self._set_row(self.pipeline_table,r,[row["name"],row["lead_count"],f"{float(row['total_value']):,.2f}",row["sequence"]])

    def reload_reports(self):
        rows=self.repo.reports(self.report_mode.currentData()); self.report_table.setRowCount(len(rows))
        for r,row in enumerate(rows): self._set_row(self.report_table,r,[row["label"],row["total"],row.get("won",0),f"{float(row.get('value',0)):,.2f}"])

    @staticmethod
    def _set_row(table,row,values):
        for c,value in enumerate(values): table.setItem(row,c,QTableWidgetItem(str(value or "")))

    def selected_lead(self):
        r=self.leads_table.currentRow()
        if r<0 or r>=len(self.leads): QMessageBox.warning(self,"تنبيه","اختر عميلًا أولًا"); return None
        return self.leads[r]

    def selected_activity(self):
        r=self.activity_table.currentRow()
        if r<0 or r>=len(self.activities): QMessageBox.warning(self,"تنبيه","اختر نشاطًا أولًا"); return None
        return self.activities[r]

    def add_lead(self):
        d=LeadDialog(self.repo,parent=self)
        if d.exec()!=QDialog.Accepted:return
        try:self.repo.save_lead(d.payload())
        except ValueError as e:QMessageBox.warning(self,"تنبيه",str(e));return
        self.reload(); QMessageBox.information(self,"تم","تم إنشاء العميل المحتمل")

    def edit_lead(self):
        lead=self.selected_lead()
        if not lead:return
        d=LeadDialog(self.repo,self.repo.get_lead(int(lead["id"])),self)
        if d.exec()!=QDialog.Accepted:return
        try:self.repo.save_lead(d.payload(),int(lead["id"]))
        except ValueError as e:QMessageBox.warning(self,"تنبيه",str(e));return
        self.reload()

    def change_stage(self):
        lead=self.selected_lead()
        if not lead:return
        stages=self.repo.list_stages(); label,ok=QInputDialog.getItem(self,"تغيير المرحلة","المرحلة الجديدة",[x["name"] for x in stages],0,False)
        if ok:self.repo.set_stage(int(lead["id"]),next(x["code"] for x in stages if x["name"]==label));self.reload()

    def add_note(self):
        lead=self.selected_lead()
        if not lead:return
        note,ok=QInputDialog.getMultiLineText(self,"ملاحظة متابعة","الملاحظة")
        if ok:
            try:self.repo.add_note(int(lead["id"]),note)
            except ValueError as e:QMessageBox.warning(self,"تنبيه",str(e));return
            self.reload()

    def schedule_activity(self):
        lead=self.selected_lead()
        if not lead:return
        d=ActivityDialog(self.repo,self)
        if d.exec()!=QDialog.Accepted:return
        try:self.repo.schedule(int(lead["id"]),str(d.kind.currentData()),d.subject.text(),d.notes.toPlainText(),d.due.dateTime().toString("yyyy-MM-ddTHH:mm:ss"),str(d.priority.currentData()),d.owner.currentData())
        except ValueError as e:QMessageBox.warning(self,"تنبيه",str(e));return
        self.reload()

    def convert_customer(self):
        lead=self.selected_lead()
        if not lead:return
        try:pid=self.repo.convert_to_customer(int(lead["id"]))
        except ValueError as e:QMessageBox.warning(self,"تنبيه",str(e));return
        self.reload();QMessageBox.information(self,"تم",f"تم تحويل العميل وربطه بشاشة العملاء رقم {pid}")

    def timeline(self):
        lead=self.selected_lead()
        if not lead:return
        d=QDialog(self);d.setWindowTitle(f"سجل العميل - {lead['name']}");d.resize(900,600)
        t=QTableWidget(0,7);t.setHorizontalHeaderLabels(["التاريخ","النوع","العنوان","الملاحظات","الموعد","الحالة","الموظف"]);self._setup_table(t)
        rows=self.repo.list_timeline(int(lead["id"]));t.setRowCount(len(rows))
        for r,row in enumerate(rows):self._set_row(t,r,[format_egypt_datetime(row["created_at"]),ACTIVITY_TYPES.get(row["activity_type"],row["activity_type"]),row["subject"],row.get("notes",""),format_egypt_datetime(row.get("due_at")),STATUS.get(row["status"],row["status"]),row.get("owner_name","")])
        b=QPushButton("إغلاق");b.clicked.connect(d.accept);lay=QVBoxLayout(d);lay.addWidget(t);lay.addWidget(b);d.exec()

    def complete_activity(self):
        a=self.selected_activity()
        if not a:return
        outcome,ok=QInputDialog.getMultiLineText(self,"إنهاء النشاط","نتيجة التواصل")
        if ok:self.repo.complete_activity(int(a["id"]),outcome);self.reload()

    def reschedule_activity(self):
        a=self.selected_activity()
        if not a:return
        d=QDialog(self);d.setWindowTitle("إعادة جدولة");due=QDateTimeEdit(datetime.now()+timedelta(days=1));due.setCalendarPopup(True);due.setDisplayFormat("yyyy-MM-dd HH:mm")
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject);lay=QVBoxLayout(d);lay.addWidget(due);lay.addWidget(buttons)
        if d.exec()==QDialog.Accepted:self.repo.reschedule(int(a["id"]),due.dateTime().toString("yyyy-MM-ddTHH:mm:ss"));self.reload()

    def cancel_activity(self):
        a=self.selected_activity()
        if a:self.repo.cancel_activity(int(a["id"]));self.reload()

    def _reminders(self):
        fresh=[x for x in self.repo.due_activities() if int(x["id"]) not in self.alerted]
        if not fresh:return
        self.alerted.update(int(x["id"]) for x in fresh);x=fresh[0]
        QMessageBox.information(self,"تذكير CRM",f"لديك متابعة مستحقة مع {x['lead_name']}\nالهاتف: {x['phone']}\nالنشاط: {x['subject']}\nالموعد: {format_egypt_datetime(x['due_at'])}")
