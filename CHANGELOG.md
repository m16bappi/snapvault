# Changelog

All notable changes to django-recovery are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [0.3.0b1] - 2026-07-17

### Changed

- Project status is beta / under active development.

## [0.2.0] - 2026-07-16

### Changed

- **Breaking:** the repository password moved out of `OPTIONS` to the
  top-level `RECOVERY['PASSWORD']` / `RECOVERY['PASSWORD_FILE']` keys.
  `password` / `password_file` inside `OPTIONS` now raise
  `ImproperlyConfigured` — `OPTIONS` carries backend connection details only.

  ```python
  # before                                  # after
  "OPTIONS": {"path": "...",                "OPTIONS": {"path": "..."},
              "password": "..."}            "PASSWORD": "..."
  ```

- Both password keys are optional: with neither set, restic reads
  `RESTIC_PASSWORD` / `RESTIC_PASSWORD_FILE` from the process environment.
- `location` is accepted only by the backends that honour it (S3, GCS,
  Azure); passing it elsewhere now raises `ImproperlyConfigured`.
- `BaseBackend` is abstract: subclasses must implement
  `get_default_options()`; the `credential_env()` hook merged into `env()`.

### Added

- `django_recovery.types` — `RecoverySettings`, `RetentionOptions`, and
  `TuningOptions` TypedDicts. Annotate `RECOVERY` for IDE autocomplete and
  static key checking; runtime validation derives from the same annotations.

## [0.1.2] - 2026-07-16

### Changed

- SQLite backups now store the raw database file instead of a `.dump` SQL
  stream, using `sqlite3.Connection.backup()` for a consistent online copy
  (WAL-safe, honours SQLite locking). The `sqlite3` CLI is no longer required.
- SQLite snapshot filename changed from `<alias>.sql` to `<alias>.sqlite3`.
  Snapshots taken with 0.1.1 or earlier must be restored with that version.

### Fixed

- `recovery init` is now idempotent: when the repository already exists it
  reports and exits successfully instead of failing with a restic error.
- SQLite restore now works over an existing database file (previously the
  `.dump` replay failed on existing tables and the CLI still exited 0).
- Backing up a missing SQLite database file now fails loudly instead of
  snapshotting a silently created empty database.

## [0.1.1] - 2026-07-15

### Added

- `RECOVERY['RETENTION']` policy and the `recovery prune` command
  (`forget --keep-* --prune`, with `--dry-run`).
- `RECOVERY['TUNING']` restic options: compression, pack size, read
  concurrency, upload/download limits, retry-lock, cache controls,
  backend connections.
- `HOST`, `SKIP_IF_UNCHANGED`, `MEDIA_EXCLUDE`, and `EXTRA_ARGS` settings.

## [0.1.0] - 2026-07-15

### Added

- Initial release: encrypted, deduplicated Django database and media backups
  powered by restic.
- PostgreSQL/PostGIS, MySQL/MariaDB, and SQLite connectors.
- Storage backends: local, S3 (and S3-compatible), GCS, Azure, SFTP, and a
  generic restic URL escape hatch.
- `manage.py recovery` command: `init`, `backup`, `restore`, `snapshots`,
  `remove`.

[0.2.0]: https://github.com/m16bappi/django-recovery/releases/tag/v0.2.0
[0.1.2]: https://github.com/m16bappi/django-recovery/releases/tag/v0.1.2
[0.1.1]: https://github.com/m16bappi/django-recovery/releases/tag/v0.1.1
[0.1.0]: https://github.com/m16bappi/django-recovery/releases/tag/v0.1.0
