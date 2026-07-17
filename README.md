# django-recovery

Encrypted, deduplicated Django database and media backups, powered by [restic](https://restic.net/).

`django-recovery` turns your Django `DATABASES` (and optionally your media directory)
into restic snapshots: always encrypted, deduplicated across backups, and restorable
through a management command.

> **Status:** 🚧 beta / under active development. APIs and settings may change before 1.0.

## Highlights

- **Encryption is always on** — every snapshot is encrypted client-side; there is no
  plaintext mode to forget to turn on.
- **Deduplication** — daily backups cost only the delta, not a full copy each time.
- **Atomic failure semantics** — a failed dump produces **no snapshot**, never a
  half-written one.
- **Any storage** — local disk, S3 (and compatibles), GCS, Azure, SFTP, or anything
  via rclone.
- **Guarded restores** — typed confirmation plus a tag guard that refuses to restore
  a snapshot into the wrong database.

## Install

```bash
pip install django-recovery
```

Requires the [restic](https://restic.net/) binary (>= 0.16) on `PATH`, plus the
command-line client for each database engine you back up (`pg_dump`/`psql`,
`mysqldump`/`mysql`, or `sqlite3`).

## Quickstart

```python
# settings.py
import os

INSTALLED_APPS = [
    # ...
    "django_recovery",
]

RECOVERY = {
    "BACKEND": "django_recovery.backends.LocalBackend",
    "OPTIONS": {"path": "/var/backups/myapp-restic"},
    "PASSWORD": os.environ["RESTIC_PASSWORD"],
    "DATABASES": ["default"],
}
```

```bash
python manage.py recovery init
python manage.py recovery backup
python manage.py recovery snapshots
```

## Documentation

Full documentation — settings reference, storage backends, management commands,
scheduling, and FAQ — lives at
**[m16bappi.github.io/django-recovery](https://m16bappi.github.io/django-recovery/)**.

## Related

- **[restic](https://restic.net/)** — the backup engine that does the real work.
- **[Source repository](https://github.com/m16bappi/django-recovery)** — issues and
  contributions welcome.
