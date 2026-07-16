# Installation

## 1. Install the package

```bash
pip install django-recovery
```

## 2. Install restic

**restic must be installed on the system** (>= 0.16, for `--stdin-from-command`) and
available on `PATH`. django-recovery does not bundle restic:

=== "Debian / Ubuntu"

    ```bash
    sudo apt-get install restic
    ```

=== "macOS"

    ```bash
    brew install restic
    ```

=== "Windows"

    ```powershell
    choco install restic
    ```

=== "Manual"

    Grab a release binary from [restic.net](https://restic.net/) and put it on `PATH`,
    or point `RECOVERY["BINARY"]` at its location.

Verify:

```bash
restic version
```

## 3. Install database CLI clients

You need the command-line client for each database engine you back up, on `PATH`:

| Engine | Clients |
|---|---|
| PostgreSQL / PostGIS | `pg_dump`, `psql` |
| MySQL | `mysqldump`, `mysql` |
| SQLite | none needed |

See [Supported databases](databases.md) for details.

## 4. Add the app

```python
INSTALLED_APPS = [
    # ...
    "django_recovery",
]
```

Run migrations (django-recovery stores a `BackupJob` row per operation for the web UI):

```bash
python manage.py migrate
```

Continue with the [Quickstart](quickstart.md).
