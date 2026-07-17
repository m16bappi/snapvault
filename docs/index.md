# Why django-recovery

!!! warning "Beta"
    django-recovery is 🚧 under active development. APIs and settings may change before 1.0.

**django-recovery** turns your Django `DATABASES` (and optionally your media directory)
into [restic](https://restic.net/) snapshots: always encrypted, deduplicated across
backups, and restorable through a management command.

You configure it like any Django storage — a backend class plus options in
`settings.py` — and get production-grade backups without writing a single shell script.
Setup lives in [Quickstart](quickstart.md); this page is the *why*.

## The problem with the usual approach

Most Django projects back up with some variant of `pg_dump | gzip > backup.sql.gz`
pushed to a bucket by cron. That script quietly accumulates failure modes:

- **A failed dump still uploads.** The dump crashes halfway, gzip happily compresses
  the fragment, and you discover the corruption months later — during a restore.
- **No encryption**, or hand-rolled GPG that someone must remember to configure.
- **Every backup is a full copy.** A 5 GB database uploaded nightly is ~150 GB of
  transfer and storage *per month*, even if 1% of the data changed.
- **Retention is another script.** Deleting old dumps safely is your job, forever.

## What restic brings

django-recovery delegates the hard parts to restic, a mature open-source backup engine,
and focuses on the Django side (dump commands built from `settings.DATABASES`,
management commands).

**Encryption is always on.** Every snapshot is encrypted client-side (AES-256 in
counter mode, authenticated with Poly1305-AES) before a single byte leaves your server —
including **metadata**: file names and structure are as unreadable as the data. There is
no plaintext mode to forget to turn off, and the storage provider never sees anything.

**Atomic failure semantics.** Backups stream through
`restic backup --stdin-from-command`: if the database dump exits non-zero, **no snapshot
is created**. A half-written backup cannot exist.

**Deduplication.** restic splits data into content-defined chunks and stores each chunk
once. Tomorrow's backup only stores what changed since today's.

**Any storage.** Local disk, S3 and every S3-compatible service, Google Cloud Storage,
Azure Blob, SFTP — plus anything else through rclone.

**Verifiable.** The repository is a documented, open format; `restic check` audits it,
and any snapshot can be mounted or dumped with plain restic — your backups are never
locked inside this library.

## How it compares

| | cron + `pg_dump \| gzip` | django-dbbackup | django-recovery |
|---|---|---|---|
| Encryption | DIY | Optional, via GPG (gpg binary + key trust setup) | Always on, client-side, zero setup |
| Failed dump | Fragment still uploads | Depends on your wiring | No snapshot — atomic by design |
| Storage cost | Full copy every run | Full copy every run | Delta only (dedup + zstd) |
| Retention | Another script | Keep-last-N count | Policy: `daily/weekly/monthly/yearly/within`, per series |
| Restore safety | Hope | Manual care | Tag guard refuses the wrong database; typed confirmation |

django-dbbackup is a solid, popular package — if plain dumps in your existing
`django-storages` bucket are all you need, it may be enough. django-recovery exists for
when you want encryption, dedup, retention, and guarded restores to be **defaults you
cannot forget**, not options you must assemble.

## What django-recovery is not

Honesty section. It is **not point-in-time recovery**: snapshots capture the moment the
dump ran, not every transaction between dumps (dedup makes hourly backups affordable,
which narrows the window — but for true PITR on a high-write PostgreSQL, reach for
WAL archiving tools like pgBackRest or WAL-G). It also does not manage restic for you
beyond what it needs: the binary is a system prerequisite, not a bundled dependency.

## Cheaper bandwidth, cheaper storage

Deduplication is not just an integrity feature — it is the single biggest lever on your
backup bill, because cloud providers charge for **stored bytes** and **transferred
bytes**, and restic minimizes both:

- **Upload only the delta.** Consecutive dumps of a mostly-static database share almost
  all their chunks. Instead of re-uploading 5 GB nightly, restic uploads roughly the
  churn — often a few dozen MB. On metered or slow links (and on providers that bill
  ingress/egress), that difference compounds every single day.
- **Store each chunk once.** Thirty daily backups of that 5 GB database are *not*
  150 GB in your bucket; they are ~5 GB plus a month of deltas. Storage grows with your
  data's change rate, not with your backup frequency.
- **Compression on top.** restic compresses chunks with zstd before upload, shrinking
  both transfer and storage again. (django-recovery deliberately streams *uncompressed*
  dumps into restic — pre-compressed data would defeat deduplication.)
- **Retention without re-uploads.** `forget --prune` drops old snapshots and reclaims
  space in place; unchanged chunks referenced by newer snapshots are untouched.

The net effect: you can afford to back up **more often** — hourly instead of nightly —
while paying less than a naive daily full-dump pipeline.

## What django-recovery adds on top

restic alone doesn't know what a Django project is. django-recovery contributes:

- **Zero-duplication configuration** — dump/restore commands are built from
  `settings.DATABASES`; credentials are never copied into a second config system.
- **Django-native setup** — a `STORAGES`-style `RECOVERY` setting with validated
  backend classes; misconfiguration fails loudly with `ImproperlyConfigured`.
- **One management command** — `recovery init|backup|restore|snapshots|remove`, with
  confirmation prompts and a tag guard that refuses to restore a snapshot into the
  wrong database.

!!! warning "One thing restic cannot recover"
    If you lose the repository password, you lose the backups. There is no reset and no
    backdoor. Store the password somewhere durable and separate from the repository.

## Next steps

- [Installation](installation.md) — install the package and the restic binary.
- [Quickstart](quickstart.md) — first backup in five minutes.
- [Storage backends](backends.md) — S3, GCS, Azure, SFTP, local, rclone.
