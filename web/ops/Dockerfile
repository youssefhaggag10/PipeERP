FROM postgres:17-alpine

RUN apk add --no-cache curl openssl \
    && mkdir -p /backups \
    && chown postgres:postgres /backups

COPY backup.sh /usr/local/bin/pipeerp-backup
COPY restore.sh /usr/local/bin/pipeerp-restore
COPY healthcheck.sh /usr/local/bin/pipeerp-healthcheck
COPY load_test.py /usr/local/bin/pipeerp-load-test
RUN chmod 0555 /usr/local/bin/pipeerp-backup /usr/local/bin/pipeerp-restore \
    /usr/local/bin/pipeerp-healthcheck /usr/local/bin/pipeerp-load-test

USER postgres
WORKDIR /backups
