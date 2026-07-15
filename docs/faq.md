# FAQ

## One repository or many?

v1 uses exactly **one** repository (the configured `BACKEND` + `OPTIONS`) for all
databases and media, separated by tags. Per-database repositories are out of scope for
now.

## Does it back up media files?

Yes — set `"MEDIA": True` and django-recovery snapshots `settings.MEDIA_ROOT` (tagged
`media`) alongside your databases.

## The repository is locked

A killed job can leave a restic lock behind. Clear it with restic directly, using the
same repository and password:

```bash
restic -r <repo> unlock
```

(There is no `recovery unlock` subcommand in v1.)

## What if I lose the repository password?

!!! danger
    You lose the backups. restic encryption is not recoverable without the password —
    no reset, no backdoor, no support ticket that can decrypt your snapshots. Store the
    password (or the password file) somewhere durable and separate from the repository
    itself.

## Why do I need restic installed separately?

Same model as django-dbbackup's dependency on `pg_dump`: the engine is a system binary,
kept out of the wheel so it can be updated independently and stays a few MB where it
belongs. See [Installation](installation.md).

## Out of scope in v1

- **Repository verification (`restic check`) command and retention UI** — retention runs
  via [`recovery prune`](commands.md#recovery-prune); a `check` subcommand and dashboard
  controls come later.
- **Scheduling** — drive `recovery backup` / `recovery prune` from cron or Celery beat.
- **Per-database separate repositories.**
- Any configuration from the UI — `settings.py` only.
