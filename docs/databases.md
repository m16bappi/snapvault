# Supported databases

| Engine (Django `ENGINE` suffix) | Dump / restore clients (must be on `PATH`) | Password via |
|---|---|---|
| `postgresql`, `postgis` | `pg_dump` / `psql` | `PGPASSWORD` |
| `mysql` | `mysqldump` / `mysql` | `MYSQL_PWD` |
| `sqlite3` | none — raw file copy via Python | — (file only) |

Connection host/port/user/name are read from each alias's `DATABASES` entry; host and
port are omitted from the command line when empty (socket connections). Any other engine
raises `NotImplementedError` naming the engine.

Database credentials are never duplicated into django-recovery configuration — the
connector reads them from `settings.DATABASES` at runtime and passes passwords to the
client via environment variables only.
