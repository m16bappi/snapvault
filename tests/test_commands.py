"""Tests for the ``recovery`` management command.

The command is a thin argparse wrapper over :mod:`django_recovery.services`;
here every service function is patched at the module level (the command imports
the ``services`` module and calls attributes on it, so patching
``django_recovery.services.<fn>`` is what the command sees). Confirmation
prompts are driven by monkeypatching ``builtins.input``. No restic binary,
database, or real snapshot is touched.

call_command note: Django's ``call_command`` handles argparse subparsers by
passing the subcommand as the first positional argument, e.g.
``call_command("recovery", "backup", database=["default"])``. Options defined
on a subparser are forwarded as keyword arguments (``database=...``,
``snapshot=...``, ``noinput=True``). The positional ``snapshot_id`` of the
``remove`` subcommand is passed as a second positional argument.
"""

from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from django_recovery import services
from django_recovery.restic import Snapshot

RECOVERY_WITH_RETENTION = {
    "BACKEND": "django_recovery.backends.LocalBackend",
    "OPTIONS": {"path": "/tmp/test-repo", "password": "test-password"},
    "RETENTION": {"daily": 7, "weekly": 4},
}


def test_backup_calls_run_backup_with_databases(monkeypatch):
    fake = MagicMock(return_value={"default": "ok"})
    monkeypatch.setattr(services, "run_backup", fake)

    call_command("recovery", "backup", database=["default"])

    fake.assert_called_once()
    _, kwargs = fake.call_args
    assert kwargs["databases"] == ["default"]


def test_snapshots_prints_table(monkeypatch, capsys):
    snap = Snapshot(
        id="abc123def456",
        short_id="abc123",
        time="2026-07-14T12:00:00Z",
        tags=["db:default", "test"],
        paths=["/db/default.sql"],
    )
    monkeypatch.setattr(
        services, "list_snapshots", MagicMock(return_value=[snap])
    )

    call_command("recovery", "snapshots")

    out = capsys.readouterr().out
    assert "abc123" in out
    assert "db:default,test" in out


def test_snapshots_empty(monkeypatch, capsys):
    monkeypatch.setattr(services, "list_snapshots", MagicMock(return_value=[]))

    call_command("recovery", "snapshots")

    assert "No snapshots." in capsys.readouterr().out


def test_restore_noinput_calls_run_restore(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_restore", fake)

    call_command(
        "recovery", "restore",
        snapshot="latest", database="default", noinput=True,
    )

    fake.assert_called_once()
    _, kwargs = fake.call_args
    assert kwargs["alias"] == "default"
    assert kwargs["snapshot_id"] == "latest"


def test_restore_mismatched_confirmation_aborts(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_restore", fake)
    monkeypatch.setattr("builtins.input", lambda prompt="": "wrong")

    with pytest.raises(CommandError):
        call_command(
            "recovery", "restore", snapshot="latest", database="default"
        )

    fake.assert_not_called()


def test_restore_matching_confirmation_runs(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_restore", fake)
    monkeypatch.setattr("builtins.input", lambda prompt="": "default")

    call_command(
        "recovery", "restore", snapshot="latest", database="default"
    )

    fake.assert_called_once()
    _, kwargs = fake.call_args
    assert kwargs["alias"] == "default"


def test_remove_noinput_calls_remove_snapshot(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "remove_snapshot", fake)

    call_command("recovery", "remove", "abc123", noinput=True)

    fake.assert_called_once()
    args, _ = fake.call_args
    assert args[0] == "abc123"


def test_remove_declined_confirmation_aborts(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "remove_snapshot", fake)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")

    with pytest.raises(CommandError):
        call_command("recovery", "remove", "abc123")

    fake.assert_not_called()


def test_init_calls_run_init(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_init", fake)

    call_command("recovery", "init")

    fake.assert_called_once()


def test_prune_without_retention_raises(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_prune", fake)

    with pytest.raises(CommandError, match="RETENTION"):
        call_command("recovery", "prune", noinput=True)

    fake.assert_not_called()


@override_settings(RECOVERY=RECOVERY_WITH_RETENTION)
def test_prune_noinput_calls_run_prune(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_prune", fake)

    call_command("recovery", "prune", noinput=True)

    fake.assert_called_once()
    assert fake.call_args.kwargs["dry_run"] is False


@override_settings(RECOVERY=RECOVERY_WITH_RETENTION)
def test_prune_declined_confirmation_aborts(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_prune", fake)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")

    with pytest.raises(CommandError):
        call_command("recovery", "prune")

    fake.assert_not_called()


@override_settings(RECOVERY=RECOVERY_WITH_RETENTION)
def test_prune_dry_run_skips_prompt(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(services, "run_prune", fake)

    def explode(prompt=""):  # pragma: no cover - must not be called
        raise AssertionError("dry-run must not prompt")

    monkeypatch.setattr("builtins.input", explode)

    call_command("recovery", "prune", dry_run=True)

    fake.assert_called_once()
    assert fake.call_args.kwargs["dry_run"] is True
