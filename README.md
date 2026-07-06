# PipeERP

برنامج ERP محلي لإدارة مصانع المواسير البلاستيك، يعمل Offline على جهاز ويندوز أو شبكة داخلية صغيرة.

## الهدف

بناء منتج قابل للبيع لأكثر من مصنع، وليس برنامج خاص بمصنع واحد فقط.

## التقنية

- Python
- PySide6
- SQLite في البداية
- واجهة عربية RTL
- قابل للتطوير لاحقًا إلى PostgreSQL أو نسخة شبكية

## أول إصدار تأسيسي

الإصدار الحالي يحتوي على:

- تشغيل تطبيق Desktop
- شاشة Login عربية
- قاعدة بيانات SQLite
- إنشاء مستخدم افتراضي
- Main Window عربي
- Dashboard أولي
- طبقة Database منفصلة
- طبقة Services منفصلة
- Password Hashing

## بيانات الدخول الافتراضية

```text
Username: admin
Password: admin123
```

## التشغيل

```bash
python -m venv .venv
source .venv/bin/activate  # Linux / macOS
# أو على Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

## المرحلة القادمة

- إدارة الأصناف
- إدارة المخازن
- المشتريات مع Lots
- التصنيع بالوزن
- الهالك وإعادة استخدامه
- تقارير المخزون والتكلفة
