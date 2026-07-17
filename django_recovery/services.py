"""Service layer orchestrating restic + connectors.

These functions are the single shared entry point for the management
commands. Each accepts an optional ``log_callback`` used to report short,
human-readable progress strings (commands print). No password material is
ever passed to the callback.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from .conf import RecoveryConfig, build_global_args, get_config, resolve_binary
from .connectors import get_connector
from .restic import Restic, Snapshot

LogCallback = Callable[[str], None]


def _noop(_message: str) -> None:
    """Default log sink: discard the message."""


def _make_restic(config: RecoveryConfig | None = None) -> Restic:
    """Build a :class:`Restic` from a (possibly default) config."""
    config = config or get_config()
    binary = resolve_binary(config)
    return Restic(
        config.backend.repository,
        extra_env=config.restic_env(),
        binary=binary,
        global_args=build_global_args(config),
    )


def run_init(
    config: RecoveryConfig | None = None,
    log_callback: LogCallback | None = None,
) -> None:
    """Initialize the restic repository.

    Idempotent: when the repository already exists the call logs and
    returns instead of failing (``restic init`` errors on an existing
    repository).
    """
    log = log_callback or _noop
    restic = _make_restic(config)
    if restic.is_initialized():
        log("Repository already initialized; skipping.")
        return None
    log("Initializing repository...")
    restic.init()
    log("Repository initialized.")
    return None


def run_backup(
    databases: list[str] | None = None,
    config: RecoveryConfig | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, str]:
    """Back up each configured database (and media, when enabled).

    Each database is streamed through ``restic backup --stdin-from-command``
    with the connector's dump command; the connector's ``extra_env`` (e.g.
    ``PGPASSWORD``) is merged into restic's environment so the dump can
    authenticate. Returns a summary dict mapping each target to ``"ok"``.
    """
    log = log_callback or _noop
    config = config or get_config()
    restic = _make_restic(config)
    databases = databases if databases is not None else config.databases

    read_concurrency = config.tuning.get("read_concurrency")

    summary: dict[str, str] = {}
    for alias in databases:
        log(f"Backing up database '{alias}'...")
        conn = get_connector(alias)
        tags = [f"db:{alias}", *config.tags]
        restic.backup_command(
            conn.dump_command(),
            stdin_filename=conn.stdin_filename,
            tags=tags,
            extra_env=conn.extra_env(),
            host=config.host,
            skip_if_unchanged=config.skip_if_unchanged,
            read_concurrency=read_concurrency,
        )
        summary[alias] = "ok"
        log(f"Database '{alias}' backed up.")

    if config.media:
        from django.conf import settings

        log("Backing up media...")
        restic.backup_paths(
            [settings.MEDIA_ROOT],
            tags=["media", *config.tags],
            host=config.host,
            skip_if_unchanged=config.skip_if_unchanged,
            read_concurrency=read_concurrency,
            exclude=config.media_exclude,
        )
        summary["media"] = "ok"
        log("Media backed up.")

    return summary


def run_restore(
    alias: str,
    snapshot_id: str,
    config: RecoveryConfig | None = None,
    log_callback: LogCallback | None = None,
) -> None:
    """Restore database ``alias`` from ``snapshot_id``.

    Guards against restoring into the wrong database: the resolved snapshot's
    tags must contain ``db:<alias>``. ``snapshot_id`` may be ``"latest"``, in
    which case the newest snapshot tagged for ``alias`` is chosen and its real
    id is used for the dump. The dump is streamed straight into the
    connector's restore command; both processes must exit zero.
    """
    log = log_callback or _noop
    config = config or get_config()
    restic = _make_restic(config)
    db_tag = f"db:{alias}"

    log(f"Resolving snapshot '{snapshot_id}' for database '{alias}'...")
    snapshots = restic.snapshots()

    snapshot = _resolve_snapshot(snapshots, snapshot_id, db_tag)
    if snapshot is None:
        raise ValueError(f"snapshot {snapshot_id} not found")
    if db_tag not in snapshot.tags:
        raise ValueError(
            f"snapshot {snapshot.short_id or snapshot.id} is not a backup of "
            f"database '{alias}'"
        )

    conn = get_connector(alias)
    log(f"Restoring database '{alias}' from snapshot {snapshot.short_id}...")
    proc = restic.dump_popen(snapshot.id, conn.stdin_filename)
    try:
        result = subprocess.run(
            conn.restore_command(),
            stdin=proc.stdout,
            env={**os.environ, **conn.extra_env()},
        )
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(
            f"restic dump failed for snapshot {snapshot.short_id} "
            f"(exit code {proc.returncode})"
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"restore of database '{alias}' failed "
            f"(exit code {result.returncode})"
        )
    log(f"Database '{alias}' restored.")
    return None


def _resolve_snapshot(
    snapshots: list[Snapshot],
    snapshot_id: str,
    db_tag: str,
) -> Snapshot | None:
    """Find the snapshot matching ``snapshot_id``.

    ``"latest"`` selects the newest snapshot carrying ``db_tag``; otherwise
    match by full ``id`` or ``short_id``.
    """
    if snapshot_id == "latest":
        candidates = [s for s in snapshots if db_tag in s.tags]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.time)
    for s in snapshots:
        if snapshot_id in (s.id, s.short_id):
            return s
    return None


def remove_snapshot(
    snapshot_id: str,
    config: RecoveryConfig | None = None,
    log_callback: LogCallback | None = None,
) -> None:
    """Forget ``snapshot_id`` and prune its now-unreferenced data."""
    log = log_callback or _noop
    restic = _make_restic(config)
    log(f"Removing snapshot {snapshot_id}...")
    restic.forget_snapshot(snapshot_id, prune=True)
    log(f"Snapshot {snapshot_id} removed.")
    return None


def run_prune(
    config: RecoveryConfig | None = None,
    dry_run: bool = False,
    log_callback: LogCallback | None = None,
) -> None:
    """Apply ``RECOVERY['RETENTION']`` with ``forget --keep-* --prune``.

    Raises:
        ValueError: when no retention policy is configured — pruning without
            a policy would be a no-op at best and surprising at worst.
    """
    log = log_callback or _noop
    config = config or get_config()
    if not config.retention:
        raise ValueError(
            "RECOVERY['RETENTION'] is not configured; nothing to prune. "
            "Add a retention policy, e.g. {'daily': 7, 'weekly': 4}."
        )
    restic = _make_restic(config)
    policy = ", ".join(f"{k}={v}" for k, v in sorted(config.retention.items()))
    verb = "Previewing" if dry_run else "Applying"
    log(f"{verb} retention policy ({policy})...")
    restic.forget_policy(config.retention, prune=not dry_run, dry_run=dry_run)
    log("Retention preview complete." if dry_run else "Retention policy applied.")
    return None


def list_snapshots(
    config: RecoveryConfig | None = None,
    log_callback: LogCallback | None = None,
) -> list[Snapshot]:
    """Return all snapshots in the repository."""
    log = log_callback or _noop
    restic = _make_restic(config)
    log("Listing snapshots...")
    return restic.snapshots()
