FROM postgres:17-alpine

RUN apk add --no-cache openssl \
    && mkdir -p /backups \
    && chown postgres:postgres /backups

COPY backup.sh /usr/local/bin/pipeerp-backup
COPY restore.sh /usr/local/bin/pipeerp-restore
RUN chmod 0555 /usr/local/bin/pipeerp-backup /usr/local/bin/pipeerp-restore

USER postgres
WORKDIR /backups
