# django-recovery

Encrypted, deduplicated Django database and media backups, powered by [restic](https://restic.net/).

`django-recovery` turns your Django `DATABASES` (and optionally your media directory)
into restic snapshots: always encrypted, deduplicated across backups, and restorable
through either a management command or a superuser-only web dashboard.

> **Status:** alpha / under active development. APIs and settings may change before 1.0.

---

## Why

Compared with rolling your own `pg_dump | gzip` cron job, recovery leans on restic for
the hard parts:

- **Encryption is always on.** Every snapshot is encrypted with your repository password.
  There is no plaintext-dump mode to forget to turn on.
- **Deduplication.** restic content-addresses data, so backing up daily costs you only
  the delta — not a full copy each time.
- **Retention lives in restic.** Snapshots are tagged and individually removable
  (`forget --prune`); you manage history with restic's proven tooling.
- **Atomic failure semantics.** Backups stream through
  `restic backup --stdin-from-command`, so if the database dump exits non-zero, **no
  snapshot is created**. You never get a half-written, silently-corrupt backup.

---

## Install

```bash
pip install django-recovery
```

---

## Prerequisites

**restic must be installed on the system** (>= 0.16, for `--stdin-from-command`) and
available on `PATH`. recovery does not bundle restic — install it yourself:

```bash
# Linux (Debian/Ubuntu)
sudo apt-get install restic

# macOS
brew install restic

# Windows
choco install restic

# or grab a release binary from https://restic.net/
```

Verify:

```bash
restic version
```

You also need the command-line client for each database engine you back up
(`pg_dump`/`psql`, `mysqldump`/`mysql`, or `sqlite3`) on `PATH` — see
[Databases supported](#databases-supported).

---

## Quickstart

**1. Add the app to `INSTALLED_APPS`:**

```python
INSTALLED_APPS = [
    # ...
    "django_recovery",
]
```

**2. Add a `RECOVERY` settings block** (same shape as Django's `STORAGES`: a backend
class plus its `OPTIONS`):

```python
import os

RECOVERY = {
    "BACKEND": "django_recovery.backends.LocalBackend",
    "OPTIONS": {
        "path": "/var/backups/myapp-restic",
        "password": os.environ["RESTIC_PASSWORD"],  # repository password
    },
    "DATABASES": ["default"],   # DATABASES aliases to back up
    "MEDIA": False,             # also back up settings.MEDIA_ROOT
    "TAGS": ["prod"],           # extra tags added to every snapshot
}
```

Everything the restic subprocess needs — repository URL and credential environment —
is built by the backend class from `OPTIONS`. Shell environment variables you may or
may not have exported do not matter; pull secrets into `OPTIONS` yourself (from
`os.environ`, a secrets manager, `django-environ`, ...).

**3. Run migrations** (recovery stores a `BackupJob` row per operation for the web UI):

```bash
python manage.py migrate
```

**4. Initialize the repository and take your first backup:**

```bash
python manage.py recovery init
python manage.py recovery backup
```

That's it. `recovery snapshots` will now list a snapshot tagged `db:default,prod`.

---

## Settings reference

All configuration lives in a single `RECOVERY` dict in `settings.py`. Nothing is
configured through the UI.

| Key         | Type        | Default       | Meaning |
|-------------|-------------|---------------|---------|
| `BACKEND`   | `str`       | *(required)*  | Dotted path to a storage backend class (see [Storage backends](#storage-backends)). |
| `OPTIONS`   | `dict`      | `{}`          | Keyword arguments for the backend class: repository location, credentials, and the repository `password` / `password_file`. |
| `DATABASES` | `list[str]` | `["default"]` | `DATABASES` aliases to back up. Each produces one snapshot tagged `db:<alias>`. |
| `MEDIA`     | `bool`      | `False`       | When `True`, also back up `settings.MEDIA_ROOT` as a snapshot tagged `media`. |
| `TAGS`      | `list[str]` | `[]`          | Extra tags appended to every snapshot (in addition to `db:<alias>` / `media`). |
| `BINARY`    | `str`       | `None`        | Explicit path to the restic binary. Overrides `PATH` discovery. |
| `RETENTION` | `dict`      | `{}`          | Retention policy for `recovery prune`, e.g. `{"daily": 7, "weekly": 4, "monthly": 6}`. Keys: `last`, `hourly`, `daily`, `weekly`, `monthly`, `yearly`, `within`. |
| `TUNING`    | `dict`      | `{}`          | restic performance flags: `compression`, `pack_size`, `read_concurrency`, `limit_upload`, `limit_download`, `retry_lock`, `cache_dir`, `no_cache`, `connections`. |
| `HOST`      | `str`       | `None`        | Stable snapshot hostname (`--host`) — set it in Docker/Kubernetes. |
| `SKIP_IF_UNCHANGED` | `bool` | `False`   | Skip snapshot creation when identical to the previous one (restic ≥ 0.17). |
| `MEDIA_EXCLUDE` | `list[str]` | `[]`      | `--exclude` patterns for the media snapshot. |
| `EXTRA_ARGS` | `list[str]` | `[]`         | Raw arguments appended to every restic invocation (escape hatch). |

Every backend accepts `password` (the repository password as a string) **or**
`password_file` (a path, mapped to restic's `RESTIC_PASSWORD_FILE`) — exactly one is
required. Unknown options, unknown top-level keys, and missing required options raise
`ImproperlyConfigured` at first use. Credentials are passed to the restic subprocess via
its environment only — never on the command line, never in logs or exception text.

---

## Storage backends

Pick the class matching where the repository lives; each accepts the common options
(`password`/`password_file`, and `location` as a prefix where noted) plus its own.

### Local directory

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.LocalBackend",
    "OPTIONS": {"path": "/var/backups/myapp-restic", "password": os.environ["RESTIC_PASSWORD"]},
}
```

### Amazon S3 (and R2, B2, Spaces, MinIO, Wasabi, ...)

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.S3Backend",
    "OPTIONS": {
        "bucket_name": "myapp-backups",
        "location": "prod",                      # optional prefix inside the bucket
        "access_key": os.environ["AWS_KEY_ID"],
        "secret_key": os.environ["AWS_SECRET"],
        "region_name": "eu-central-1",           # optional
        # S3-compatible services: point endpoint_url at them
        # "endpoint_url": "https://<accountid>.r2.cloudflarestorage.com",
        "password": os.environ["RESTIC_PASSWORD"],
    },
}
```

### Google Cloud Storage

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.GCSBackend",
    "OPTIONS": {
        "bucket_name": "myapp-backups",
        "location": "prod",
        "project_id": "my-project-123456",                    # optional
        "credentials_file": "/etc/secrets/gcs-key.json",      # omit on GCE/GKE/Cloud Run (ADC)
        "password": os.environ["RESTIC_PASSWORD"],
    },
}
```

### Azure Blob Storage

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.AzureBackend",
    "OPTIONS": {
        "container": "backups",
        "location": "prod",
        "account_name": "myaccount",
        "account_key": os.environ["AZURE_KEY"],   # or "sas_token": ...
        "password": os.environ["RESTIC_PASSWORD"],
    },
}
```

### SFTP

Key/agent authentication only (restic drives the system `ssh`); password auth is not
supported.

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.SFTPBackend",
    "OPTIONS": {
        "host": "backup.example.com",
        "user": "deploy",
        "path": "/srv/restic/myapp",
        "password": os.environ["RESTIC_PASSWORD"],   # repository password, not SSH
    },
}
```

### Anything else (rclone, rest-server, Swift, ...)

`GenericBackend` passes a raw restic repository URL through verbatim, with optional
extra environment variables:

```python
RECOVERY = {
    "BACKEND": "django_recovery.backends.GenericBackend",
    "OPTIONS": {
        "repository": "rclone:mydropbox:backups/myapp",
        "extra_env": {"RCLONE_CONFIG": "/etc/rclone.conf"},   # optional
        "password": os.environ["RESTIC_PASSWORD"],
    },
}
```

---

## Management commands

A single command, `manage.py recovery`, exposes every operation through subcommands.
Progress is printed to stdout as it happens.

### `recovery init`

Initialize the restic repository defined by the configured storage backend.

```bash
python manage.py recovery init
```

### `recovery backup`

Back up every configured database (and media, if `media=True`). Repeat `--database` to
limit the run to specific aliases.

```bash
python manage.py recovery backup
python manage.py recovery backup --database default --database analytics
```

### `recovery snapshots`

List snapshots in the repository (short id, time, tags, first path).

```bash
python manage.py recovery snapshots
```

### `recovery restore`

Restore a database from a snapshot. `--snapshot` accepts a snapshot id/short id or the
literal `latest` (newest snapshot tagged for that alias).

```bash
python manage.py recovery restore --snapshot latest --database default
```

By default this prompts before overwriting:

```
This will OVERWRITE database 'default'. Type the alias to continue:
```

You must type the alias exactly (`default`) to proceed; anything else aborts with a
non-zero exit code and **no** service call. Pass `--noinput` to skip the prompt (for
scripts):

```bash
python manage.py recovery restore --snapshot latest --database default --noinput
```

Restore also enforces a **tag guard**: it refuses to load a snapshot into a database
whose `db:<alias>` tag it does not carry, so you cannot accidentally restore the
`analytics` dump into `default`.

### `recovery remove`

Permanently forget a snapshot and prune its now-unreferenced data.

```bash
python manage.py recovery remove 1a2b3c4d
```

Prompts for confirmation (`Permanently remove snapshot <id>? Type 'yes' to continue:`);
type `yes` to proceed. Pass `--noinput` to skip:

```bash
python manage.py recovery remove 1a2b3c4d --noinput
```

### `recovery prune`

Apply the `RECOVERY["RETENTION"]` policy: forget snapshots outside it and reclaim space
(`restic forget --keep-* --prune`, grouped by `paths,tags` so each database/media series
is retained independently).

```bash
python manage.py recovery prune --dry-run   # preview, removes nothing
python manage.py recovery prune             # prompts for confirmation
python manage.py recovery prune --noinput   # for cron
```

Refuses to run when `RETENTION` is not configured.

---

## Web UI

A superuser-only dashboard exposes exactly four operations — **show snapshots, backup,
restore, remove** — with zero configuration surface (everything comes from
`settings.RECOVERY`).

**Mount it** in your project's `urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    # ...
    path("recovery/", include("django_recovery.urls")),
]
```

Then visit `/recovery/` as a superuser. Access control is strict: anonymous users are
redirected to login, and authenticated **non-superusers get a hard 403** (backups are
credentials-grade power, so `is_staff` is deliberately not enough).

The four operations:

- **Show** — the dashboard lists snapshots (id, time, tags, paths) and recent jobs.
- **Backup** — a single "Backup now" button launches a backup job.
- **Restore** — a per-snapshot form requires you to type the target alias into a
  confirmation field that must match the selected database, or the request is rejected.
- **Remove** — a per-snapshot form with an explicit confirmation checkbox.

Long-running operations run in a background thread as a `BackupJob`; the job page polls a
JSON status endpoint every 2 seconds and streams the live log. Only one job runs at a
time — a second launch while a job is active is refused with a banner message.

> _(No screenshot yet — the dashboard shows the snapshot table with per-snapshot
> restore/remove actions, a top "Backup now" button, and a recent-jobs table with status
> badges linking to live logs.)_

---

## How it works

**Backup:** for each configured alias, recovery asks the engine connector for a dump
command (`pg_dump …`, `mysqldump …`, `sqlite3 … .dump`) and hands it to restic:

```
restic --json -r <repo> backup --stdin-filename <alias>.sql \
       --tag db:<alias> [--tag <your tags>] --stdin-from-command -- <dump command…>
```

Because restic runs the dump itself and only snapshots its stdout, a **failed dump
produces no snapshot**. Database passwords are passed to the dump out-of-band via
environment variables (`PGPASSWORD`, `MYSQL_PWD`), never on the command line, and never
appear in logs or exception text.

**Restore:** recovery resolves the snapshot, verifies the `db:<alias>` **tag guard**,
then streams:

```
restic dump <snapshot> <alias>.sql   |   <restore command, e.g. psql -d db …>
```

The dump bytes flow straight into the restore client's stdin. Both processes must exit
zero or the restore is reported as failed.

**Tags:** every database snapshot is tagged `db:<alias>` plus any `RECOVERY["TAGS"]`;
media snapshots are tagged `media`. Tags drive `latest` resolution and the restore guard.

---

## Databases supported

| Engine (Django `ENGINE` suffix) | Dump / restore clients (must be on `PATH`) | Password via |
|---|---|---|
| `postgresql`, `postgis`         | `pg_dump` / `psql`                          | `PGPASSWORD` |
| `mysql`                         | `mysqldump` / `mysql`                        | `MYSQL_PWD`  |
| `sqlite3`                       | `sqlite3`                                    | — (file only) |

Connection host/port/user/name are read from each alias's `DATABASES` entry; host and
port are omitted from the command line when empty (socket connections). Any other engine
raises `NotImplementedError` naming the engine.

---

## FAQ

**One repository or many?** v1 uses exactly **one** repository (the configured
`BACKEND` + `OPTIONS`) for all databases and media, separated by tags. Per-database
repositories are out of scope for now.

**Does it back up media files?** Yes — set `"MEDIA": True` and recovery snapshots
`settings.MEDIA_ROOT` (tagged `media`) alongside your databases.

**The repository is locked** (e.g. a job was killed). restic leaves a lock behind; clear
it with restic directly — `restic -r <repo> unlock` — using the same password. (There is
no `recovery unlock` subcommand in v1.)

> **⚠️ If you lose the repository password, you lose the backups.** restic encryption is
> not recoverable without the password — there is no reset, no backdoor, no support ticket
> that can decrypt your snapshots. Store `RESTIC_PASSWORD` (or your password file) somewhere
> durable and separate from the repository itself.

---

## Out of scope in v1

- **Repository verification (`restic check`) command and retention UI** — retention runs
  via `recovery prune`; a `check` subcommand and dashboard controls come later.
- **Scheduling** — recovery does not run itself. Drive it from cron or Celery beat, e.g.
  nightly `0 2 * * *  cd /app && python manage.py recovery backup` plus weekly
  `0 4 * * 0  cd /app && python manage.py recovery prune --noinput`.
- **Per-database separate repositories** — one repository per project in v1.
- Any configuration from the UI — `settings.py` only.

---

## Related

- **[restic](https://restic.net/)** — the backup program that does the real work.
- **[Source repository](https://github.com/m16bappi/django-recovery)** — issues and
  contributions welcome at [m16bappi/django-recovery](https://github.com/m16bappi/django-recovery).
