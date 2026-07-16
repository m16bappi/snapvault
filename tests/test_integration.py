"""End-to-end integration test: real restic binary + real sqlite round-trip.

This is the release gate for Phase 2. It exercises the full backup/restore
path against a real restic repository and a real on-disk SQLite database,
using the actual ``restic`` executable (no mocking). SQLite dump/restore
runs through the connector's Python scripts — no ``sqlite3`` CLI involved.

It deliberately does NOT use Django's test-runner database (an in-memory
``:memory:`` DB is invisible to the connector's separate dump process).
Instead it builds a standalone sqlite file, points
``settings.DATABASES['default']`` at it via ``override_settings``, and
passes an explicit :class:`RecoveryConfig` to the service layer. No ORM
access, so ``django_db`` is not needed.

Skipped when the restic binary is unavailable; run explicitly with
``pytest -m integration``.
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest
from django.test import override_settings

from django_recovery import services
from django_recovery.backends import LocalBackend
from django_recovery.conf import RecoveryConfig


def _restic_binary() -> str | None:
    """Locate a real restic binary on ``PATH``, or ``None`` if unavailable."""
    return shutil.which("restic")


RESTIC_BIN = _restic_binary()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(RESTIC_BIN is None, reason="restic binary not available"),
]


def _note_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT count(*) FROM note").fetchone()[0]
    finally:
        conn.close()


def _note_bodies(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[0] for row in conn.execute("SELECT body FROM note ORDER BY id")]
    finally:
        conn.close()


def test_sqlite_backup_restore_roundtrip(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    db_path = tmp_path / "app.sqlite3"

    config = RecoveryConfig(
        backend=LocalBackend(path=str(repo), password="test-pass"),
        databases=["default"],
        media=False,
        tags=["itest"],
        binary=RESTIC_BIN,
    )

    # -- seed a real sqlite database with one row -------------------------
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE note(id INTEGER PRIMARY KEY, body TEXT)")
    conn.execute("INSERT INTO note(body) VALUES (?)", ("hello-restic",))
    conn.commit()
    conn.close()
    assert _note_bodies(str(db_path)) == ["hello-restic"]

    new_databases = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(db_path),
        }
    }

    with override_settings(DATABASES=new_databases):
        # -- init + backup ------------------------------------------------
        services.run_init(config)
        services.run_backup(config=config)

        snapshots = services.list_snapshots(config=config)
        assert len(snapshots) == 1
        assert "db:default" in snapshots[0].tags
        assert "itest" in snapshots[0].tags

        # -- mutate the DB so restore has an observable effect ------------
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM note")
        conn.commit()
        conn.close()
        assert _note_count(str(db_path)) == 0

        # -- restore over the EXISTING, mutated database file -------------
        services.run_restore("default", "latest", config=config)

        assert db_path.exists()
        assert _note_bodies(str(db_path)) == ["hello-restic"]

        # -- remove the snapshot ------------------------------------------
        services.remove_snapshot(snapshots[0].id, config=config)
        assert services.list_snapshots(config=config) == []
