# How it works

## Backup

For each configured alias, django-recovery asks the engine connector for a dump command
(`pg_dump …`, `mysqldump …`; SQLite streams its raw file) and hands it to restic:

```
restic --json -r <repo> backup --stdin-filename <alias>.sql \
       --tag db:<alias> [--tag <your tags>] --stdin-from-command -- <dump command…>
```

Because restic runs the dump itself and only snapshots its stdout:

- a **failed dump produces no snapshot** — the classic "empty dump saved as a valid
  backup" failure mode cannot happen;
- the dump **streams** into the repository — no intermediate file on disk, no temp-space
  sizing problems.

Database passwords are passed to the dump out-of-band via environment variables
(`PGPASSWORD`, `MYSQL_PWD`), never on the command line, and never appear in logs or
exception text.

## Restore

django-recovery resolves the snapshot, verifies the `db:<alias>` **tag guard**, then
streams:

```
restic dump <snapshot> <alias>.sql   |   <restore command, e.g. psql -d db …>
```

The dump bytes flow straight into the restore client's stdin. Both processes must exit
zero or the restore is reported as failed.

## Tags

Every database snapshot is tagged `db:<alias>` plus any `RECOVERY["TAGS"]`; media
snapshots are tagged `media`. Tags drive `latest` resolution and the restore guard.

## Credentials flow

The configured [storage backend](backends.md) builds the restic subprocess environment
from `OPTIONS`: repository password (`RESTIC_PASSWORD` / `RESTIC_PASSWORD_FILE`) and
cloud credentials (`AWS_*`, `GOOGLE_*`, `AZURE_*`). Backend values override anything
inherited from the shell, so behavior is deterministic regardless of the caller's
environment. Nothing secret ever enters argv.

## Why dumps are not pre-compressed

restic deduplicates by content-defined chunking. Compressed streams change completely
after any edit, which would destroy chunk reuse between consecutive backups — so
django-recovery streams raw SQL and lets restic compress (zstd) *after* chunking.
Result: deduplication **and** compression, instead of one or the other.
