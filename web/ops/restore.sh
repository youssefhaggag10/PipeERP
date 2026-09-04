#!/bin/sh
set -eu

umask 077

[ "${ALLOW_DESTRUCTIVE_RESTORE:-}" = "YES" ] || {
  echo "اضبط ALLOW_DESTRUCTIVE_RESTORE=YES بعد التأكد أن الهدف قاعدة استعادة منفصلة" >&2
  exit 1
}

backup_file=${1:-}
restore_url_file=${RESTORE_DATABASE_URL_FILE:-/run/secrets/restore_database_url}
encryption_key_file=${BACKUP_ENCRYPTION_KEY_FILE:-/run/secrets/backup_encryption_key}

[ -n "$backup_file" ] && [ -r "$backup_file" ] || { echo "ملف النسخة مطلوب وغير مقروء" >&2; exit 1; }
[ -r "$backup_file.sha256" ] || { echo "ملف checksum مفقود" >&2; exit 1; }
[ -r "$restore_url_file" ] || { echo "ملف اتصال قاعدة الاستعادة غير مقروء" >&2; exit 1; }
[ -r "$encryption_key_file" ] || { echo "ملف مفتاح التشفير غير مقروء" >&2; exit 1; }

(cd "$(dirname "$backup_file")" && sha256sum -c "$(basename "$backup_file").sha256")
restore_url=$(sed -e 's/[[:space:]]*$//' "$restore_url_file")
expected_database=${RESTORE_TARGET_DATABASE:-}
[ -n "$expected_database" ] || { echo "RESTORE_TARGET_DATABASE مطلوب" >&2; exit 1; }
actual_database=$(psql "$restore_url" -v ON_ERROR_STOP=1 -Atc "SELECT current_database();")
[ "$actual_database" = "$expected_database" ] || {
  echo "قاعدة الهدف الفعلية لا تطابق RESTORE_TARGET_DATABASE" >&2
  exit 1
}
temporary_dump=$(mktemp /tmp/pipeerp-restore.XXXXXX)
trap 'rm -f "$temporary_dump"' EXIT HUP INT TERM

openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "$backup_file" -out "$temporary_dump" -pass "file:$encryption_key_file"
pg_restore --list "$temporary_dump" >/dev/null
pg_restore --clean --if-exists --no-owner --no-privileges \
  --exit-on-error --single-transaction --dbname="$restore_url" "$temporary_dump"
psql "$restore_url" -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) AS alembic_rows FROM alembic_version;"

echo "تمت الاستعادة والتحقق من مخطط Alembic بنجاح"
