"""Tests for the service layer.

The service layer is exercised in isolation: the :class:`Restic` class and the
:func:`get_connector` factory are patched inside ``django_recovery.services``,
and ``subprocess.run`` is patched for the restore path. No real restic binary,
database, or connector is required. An explicit :class:`RecoveryConfig` (with
``binary`` set) is passed into every call so binary resolution is a no-op.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.test import override_settings

from django_recovery import services
from django_recovery.backends import LocalBackend
from django_recovery.conf import RecoveryConfig
from django_recovery.restic import Snapshot


def _config(*, databases=("default",), media=False, tags=("test",), **extra):
    return RecoveryConfig(
        backend=LocalBackend(path="/repo", password="test-password"),
        databases=list(databases),
        media=media,
        tags=list(tags),
        binary="/usr/bin/restic",
        **extra,
    )


def _connector(*, dump=None, restore=None, extra_env=None, stdin="default.sql"):
    return SimpleNamespace(
        dump_command=lambda: list(dump or ["sqlite3", "db", ".dump"]),
        restore_command=lambda: list(restore or ["sqlite3", "db"]),
        extra_env=lambda: dict(extra_env or {}),
        stdin_filename=stdin,
    )


@pytest.fixture
def mock_restic(monkeypatch):
    """Patch services.Restic; return the mock instance _make_restic yields."""
    instance = MagicMock(name="restic_instance")
    cls = MagicMock(name="Restic", return_value=instance)
    monkeypatch.setattr(services, "Restic", cls)
    return instance


@pytest.fixture
def mock_get_connector(monkeypatch):
    conn = _connector()
    factory = MagicMock(return_value=conn)
    monkeypatch.setattr(services, "get_connector", factory)
    factory.connector = conn
    return factory


# --- run_backup ------------------------------------------------------------

def test_run_backup_calls_backup_command_with_tags_and_extra_env(
    mock_restic, monkeypatch
):
    conn = _connector(
        dump=["pg_dump", "-d", "appdb"],
        extra_env={"PGPASSWORD": "secret"},
        stdin="default.sql",
    )
    monkeypatch.setattr(services, "get_connector", MagicMock(return_value=conn))

    summary = services.run_backup(config=_config())

    mock_restic.backup_command.assert_called_once_with(
        ["pg_dump", "-d", "appdb"],
        stdin_filename="default.sql",
        tags=["db:default", "test"],
        extra_env={"PGPASSWORD": "secret"},
        host=None,
        skip_if_unchanged=False,
        read_concurrency=None,
    )
    mock_restic.backup_paths.assert_not_called()
    assert summary == {"default": "ok"}


@override_settings(MEDIA_ROOT="/srv/media")
def test_run_backup_with_media_also_backs_up_media(mock_restic, mock_get_connector):
    summary = services.run_backup(
        config=_config(media=True, media_exclude=["*.tmp"])
    )

    mock_restic.backup_paths.assert_called_once_with(
        ["/srv/media"],
        tags=["media", "test"],
        host=None,
        skip_if_unchanged=False,
        read_concurrency=None,
        exclude=["*.tmp"],
    )
    assert summary == {"default": "ok", "media": "ok"}


def test_run_backup_forwards_host_and_tuning(mock_restic, mock_get_connector):
    services.run_backup(
        config=_config(
            host="web1",
            skip_if_unchanged=True,
            tuning={"read_concurrency": 4},
        )
    )
    kwargs = mock_restic.backup_command.call_args.kwargs
    assert kwargs["host"] == "web1"
    assert kwargs["skip_if_unchanged"] is True
    assert kwargs["read_concurrency"] == 4


def test_run_backup_invokes_log_callback(mock_restic, mock_get_connector):
    logs = []
    services.run_backup(config=_config(), log_callback=logs.append)
    assert logs  # at least one progress message emitted


# --- run_restore -----------------------------------------------------------

def test_run_restore_refuses_wrong_database_tag(mock_restic, monkeypatch):
    mock_restic.snapshots.return_value = [
        Snapshot(id="abc123def456", short_id="abc123", time="t",
                 tags=["db:other"]),
    ]
    conn = _connector()
    monkeypatch.setattr(services, "get_connector", MagicMock(return_value=conn))
    fake_run = MagicMock()
    monkeypatch.setattr(services.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="not a backup of database 'default'"):
        services.run_restore("default", "abc123", config=_config())

    mock_restic.dump_popen.assert_not_called()
    fake_run.assert_not_called()


def test_run_restore_happy_path_pipes_dump_into_restore(mock_restic, monkeypatch):
    mock_restic.snapshots.return_value = [
        Snapshot(id="abc123def456", short_id="abc123", time="t",
                 tags=["db:default", "test"]),
    ]
    fake_popen = SimpleNamespace(
        stdout=MagicMock(),
        returncode=0,
        wait=MagicMock(return_value=0),
    )
    mock_restic.dump_popen.return_value = fake_popen

    conn = _connector(restore=["psql", "-d", "appdb"], extra_env={"PGPASSWORD": "s"})
    monkeypatch.setattr(services, "get_connector", MagicMock(return_value=conn))

    fake_run = MagicMock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(services.subprocess, "run", fake_run)

    services.run_restore("default", "abc123", config=_config())

    # dump reads from the full snapshot id, not the short id.
    mock_restic.dump_popen.assert_called_once_with("abc123def456", "default.sql")

    args, kwargs = fake_run.call_args
    assert args[0] == ["psql", "-d", "appdb"]
    assert kwargs["stdin"] is fake_popen.stdout
    assert kwargs["env"]["PGPASSWORD"] == "s"
    fake_popen.wait.assert_called_once()


def test_run_restore_latest_resolves_newest_matching(mock_restic, monkeypatch):
    mock_restic.snapshots.return_value = [
        Snapshot(id="old111", short_id="old", time="2026-07-14T10:00:00Z",
                 tags=["db:default"]),
        Snapshot(id="new222", short_id="new", time="2026-07-14T12:00:00Z",
                 tags=["db:default"]),
        Snapshot(id="other333", short_id="oth", time="2026-07-14T13:00:00Z",
                 tags=["db:other"]),
    ]
    fake_popen = SimpleNamespace(
        stdout=MagicMock(), returncode=0, wait=MagicMock(return_value=0)
    )
    mock_restic.dump_popen.return_value = fake_popen
    monkeypatch.setattr(services, "get_connector", MagicMock(return_value=_connector()))
    monkeypatch.setattr(
        services.subprocess, "run",
        MagicMock(return_value=SimpleNamespace(returncode=0)),
    )

    services.run_restore("default", "latest", config=_config())

    mock_restic.dump_popen.assert_called_once_with("new222", "default.sql")


# --- run_prune ----------------------------------------------------------------

def test_run_prune_applies_policy(mock_restic):
    services.run_prune(config=_config(retention={"daily": 7, "weekly": 4}))
    mock_restic.forget_policy.assert_called_once_with(
        {"daily": 7, "weekly": 4}, prune=True, dry_run=False
    )


def test_run_prune_dry_run_disables_prune(mock_restic):
    services.run_prune(config=_config(retention={"daily": 7}), dry_run=True)
    mock_restic.forget_policy.assert_called_once_with(
        {"daily": 7}, prune=False, dry_run=True
    )


def test_run_prune_without_retention_raises(mock_restic):
    with pytest.raises(ValueError, match="RETENTION"):
        services.run_prune(config=_config())
    mock_restic.forget_policy.assert_not_called()


# --- remove / list / init --------------------------------------------------

def test_remove_snapshot_calls_forget(mock_restic):
    services.remove_snapshot("abc123", config=_config())
    mock_restic.forget_snapshot.assert_called_once_with("abc123", prune=True)


def test_list_snapshots_returns_restic_snapshots(mock_restic):
    snaps = [Snapshot(id="x", short_id="x", time="t")]
    mock_restic.snapshots.return_value = snaps
    assert services.list_snapshots(config=_config()) is snaps


def test_run_init_calls_restic_init(mock_restic):
    mock_restic.is_initialized.return_value = False
    services.run_init(config=_config())
    mock_restic.init.assert_called_once_with()


def test_run_init_skips_when_already_initialized(mock_restic):
    mock_restic.is_initialized.return_value = True
    messages = []
    services.run_init(config=_config(), log_callback=messages.append)
    mock_restic.init.assert_not_called()
    assert messages == ["Repository already initialized; skipping."]
