# دليل تشغيل ونشر PipeERP Web

## متطلبات الخادم

- VPS Linux مدعوم بتحديثات أمان، Docker Engine وDocker Compose v2.
- نطاق يشير إلى عنوان الخادم، ومنافذ `80/443` متاحة؛ SSH مقيد بمفاتيح ومستخدم إداري.
- مساحة منفصلة أو وجهة خارجية لنسخ PostgreSQL؛ الاحتفاظ على نفس القرص وحده غير كافٍ.

## تجهيز الملفات

داخل `web/`:

```bash
cp .env.production.example .env.production
mkdir -p secrets
chmod 0700 secrets
umask 077
openssl rand -base64 48 > secrets/secret_key
openssl rand -base64 48 > secrets/backup_encryption_key
openssl rand -base64 32 > secrets/postgres_password
```

أنشئ `secrets/database_url` بصيغة
`postgresql+psycopg://USER:PASSWORD@database:5432/DATABASE` دون طباعة كلمة المرور في
سجل الأوامر، ثم اجعل ملفات `secrets/` بصلاحية `0600`. حدّث النطاق وCORS في
`.env.production`. لا ترفع هذين المسارين إلى Git.

## فحص ما قبل النشر

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
docker compose --env-file .env.production -f compose.production.yaml build
docker compose --env-file .env.production -f compose.production.yaml run --rm migrate
```

راجع أن DNS صحيح، وأن آخر CI أخضر، وأن نسخة قاعدة النظام الحالية موجودة وقابلة للاستعادة.

## الإطلاق

```bash
docker compose --env-file .env.production -f compose.production.yaml up -d
docker compose --env-file .env.production -f compose.production.yaml ps
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 backend edge
```

تحقق من `https://DOMAIN/api/v1/health` و`/health/ready`، ثم نفذ قائمة UAT المختصرة قبل
فتح النظام للمستخدمين.

## النسخ الاحتياطي

تشغيل نسخة يدوية:

```bash
docker compose --env-file .env.production -f compose.production.yaml --profile ops run --rm backup
```

شغّل الأمر يوميًا عبر systemd timer أو جدولة موثوقة، وانقل النسخة المشفرة وملف `.sha256`
إلى وجهة خارج الـVPS. لا تنقل مفتاح التشفير مع النسخ في المكان نفسه.

## اختبار الاستعادة

1. أنشئ قاعدة PostgreSQL منفصلة باسم واضح مثل `pipeerp_restore_test`.
2. أنشئ secret مؤقتًا لاتصال هذه القاعدة ولا تستخدم اتصال الإنتاج.
3. شغّل حاوية `ops` مع:
   `ALLOW_DESTRUCTIVE_RESTORE=YES` و`RESTORE_TARGET_DATABASE=pipeerp_restore_test`.
4. نفذ `pipeerp-restore /backups/اسم-النسخة.dump.enc`.
5. تحقق من Alembic، وعدد المستخدمين والمستندات، ثم احذف قاعدة الاختبار فقط.

## rollback

- لا تُرجع migration عكسيًا على بيانات الإنتاج تلقائيًا.
- عند فشل إصدار جديد: أوقف استقبال المستخدمين، احتفظ بالسجلات، أعد صورة التطبيق السابقة،
  وإذا غيّر الإصدار البيانات فاستعد النسخة السابقة إلى قاعدة منفصلة أولًا للتحقق.
- سجل وقت العطل، الإصدار، قرار الاستعادة، ونتيجة فحص المخزون والحسابات بعد الرجوع.

## استجابة الحوادث

- تسريب سر: اعزل الخدمة، دوّر السر والجلسات، افحص سجل التدقيق، ثم أعد التشغيل.
- فشل readiness: لا تعِد تشغيل قاعدة البيانات عشوائيًا؛ افحص المساحة والاتصالات والسجلات.
- امتلاء القرص: أوقف العمليات الكتابية، حافظ على النسخ، وعالج السجلات وفق سياسة الاحتفاظ.
- اختلاف رصيد: امنع التعديل على المستند المتأثر، احفظ الأدلة، ولا تصلح قاعدة البيانات يدويًا.
