# Scheduling backups

django-recovery does not ship a scheduler — it plugs into whatever already runs your
periodic work. Two common setups:

## Linux crontab

Call the management command directly. Use absolute paths (cron runs with a minimal
environment) and `--noinput` for anything that would prompt.

```cron
# crontab -e  (as the user that runs Django)

# nightly backup at 02:00
0 2 * * * cd /srv/myapp && /srv/myapp/.venv/bin/python manage.py recovery backup >> /var/log/recovery.log 2>&1

# weekly prune, Mondays at 03:00
0 3 * * 1 cd /srv/myapp && /srv/myapp/.venv/bin/python manage.py recovery prune --noinput >> /var/log/recovery.log 2>&1
```

Cron's `PATH` is usually just `/usr/bin:/bin` — if `restic` or `pg_dump` live elsewhere,
set it at the top of the crontab:

```cron
PATH=/usr/local/bin:/usr/bin:/bin
```

## Celery

The service layer is plain functions, so tasks are thin wrappers. In your project:

```python
# myapp/tasks.py
from celery import shared_task

from django_recovery import services


@shared_task
def recovery_backup():
    return services.run_backup()   # {"default": "ok", "media": "ok"}


@shared_task
def recovery_prune():
    services.run_prune()
```

```python
# settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "recovery-backup": {
        "task": "myapp.tasks.recovery_backup",
        "schedule": crontab(hour=2, minute=0),
    },
    "recovery-prune": {
        "task": "myapp.tasks.recovery_prune",
        "schedule": crontab(hour=3, minute=0, day_of_week=1),
    },
}
```

Configuration comes from `settings.RECOVERY` as everywhere else — the tasks need
nothing extra.

## Notes for both

- The process running the schedule (cron job, celery worker) needs `restic` and the
  database client tools on its `PATH`, plus `RESTIC_PASSWORD` if you source the
  password from the environment.
- Overlapping operations are safe: restic locks the repository. Set
  `TUNING: {"retry_lock": "5m"}` so a second operation waits instead of failing.
- Workers on a different host than the web app? Set `RECOVERY["HOST"]` so snapshots
  stay in one series and [retention grouping](configuration.md#retention-policy)
  works as expected.
