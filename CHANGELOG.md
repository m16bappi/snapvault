# Changelog

All notable changes to django-recovery are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

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
- Staff web UI with background jobs and live logs.

[0.1.2]: https://github.com/m16bappi/django-recovery/releases/tag/v0.1.2
[0.1.1]: https://github.com/m16bappi/django-recovery/releases/tag/v0.1.1
[0.1.0]: https://github.com/m16bappi/django-recovery/releases/tag/v0.1.0
