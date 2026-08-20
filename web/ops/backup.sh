#!/bin/sh
set -eu

umask 077

database_url_file=${DATABASE_URL_FILE:-/run/secrets/database_url}
encryption_key_file=${BACKUP_ENCRYPTION_KEY_FILE:-/run/secrets/backup_encryption_key}
backup_dir=${BACKUP_DIR:-/backups}
retention_days=${BACKUP_RETENTION_DAYS:-14}

case "$backup_dir" in
  /|"") echo "BACKUP_DIR غير آمن" >&2; exit 1 ;;
esac
case "$retention_days" in
  *[!0-9]*|"") echo "BACKUP_RETENTION_DAYS يجب أن يكون عددًا صحيحًا" >&2; exit 1 ;;
esac
[ -r "$database_url_file" ] || { echo "ملف اتصال قاعدة البيانات غير مقروء" >&2; exit 1; }
[ -r "$encryption_key_file" ] || { echo "ملف مفتاح تشفير النسخة غير مقروء" >&2; exit 1; }
mkdir -p "$backup_dir"

database_url=$(sed -e 's/[[:space:]]*$//' "$database_url_file")
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_file="$backup_dir/pipeerp-$timestamp.dump.enc"
temporary_dump=$(mktemp "$backup_dir/.pipeerp-dump.XXXXXX")
temporary_encrypted=$(mktemp "$backup_dir/.pipeerp-encrypted.XXXXXX")

cleanup() {
  rm -f "$temporary_dump" "$temporary_encrypted"
}
trap cleanup EXIT HUP INT TERM

pg_dump --format=custom --compress=gzip:6 --no-owner --no-privileges \
  --file="$temporary_dump" "$database_url"
pg_restore --list "$temporary_dump" >/dev/null
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -in "$temporary_dump" -out "$temporary_encrypted" -pass "file:$encryption_key_file"
mv "$temporary_encrypted" "$final_file"
(
  cd "$backup_dir"
  final_name=$(basename "$final_file")
  sha256sum "$final_name" >"$final_name.sha256"
)

find "$backup_dir" -maxdepth 1 -type f \
  \( -name 'pipeerp-*.dump.enc' -o -name 'pipeerp-*.dump.enc.sha256' \) \
  -mtime "+$retention_days" -delete

echo "$final_file"
