# Management commands

A single command, `manage.py recovery`, exposes every operation through subcommands.
Progress is printed to stdout as it happens.

## `recovery init`

Initialize the restic repository defined by the configured storage backend. Run once.

```bash
python manage.py recovery init
```

## `recovery backup`

Back up every configured database (and media, if `MEDIA: True`). Repeat `--database` to
limit the run to specific aliases.

```bash
python manage.py recovery backup
python manage.py recovery backup --database default --database analytics
```

## `recovery snapshots`

List snapshots in the repository (short id, time, tags, first path).

```bash
python manage.py recovery snapshots
```

## `recovery restore`

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

!!! note "Tag guard"
    Restore refuses to load a snapshot into a database whose `db:<alias>` tag it does
    not carry — you cannot accidentally restore the `analytics` dump into `default`.

## `recovery remove`

Permanently forget a snapshot and prune its now-unreferenced data.

```bash
python manage.py recovery remove 1a2b3c4d
```

Prompts for confirmation (`Permanently remove snapshot <id>? Type 'yes' to continue:`).
Pass `--noinput` to skip:

```bash
python manage.py recovery remove 1a2b3c4d --noinput
```

## `recovery prune`

Apply the [`RETENTION` policy](configuration.md#retention-policy): forget snapshots
falling outside it and reclaim their space (`restic forget --keep-* --prune`).

```bash
python manage.py recovery prune --dry-run   # preview only, removes nothing, no prompt
python manage.py recovery prune             # prompts for confirmation
python manage.py recovery prune --noinput   # for cron
```

Without `RECOVERY["RETENTION"]` configured the command refuses to run. The interactive
prompt shows the policy and requires typing `yes`.

## Scheduling

django-recovery does not run itself. Drive `recovery backup` (and a periodic
`recovery prune`) from cron or Celery beat:

```cron
0 2 * * *  cd /app && python manage.py recovery backup
0 4 * * 0  cd /app && python manage.py recovery prune --noinput
```
