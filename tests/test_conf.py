import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from django_recovery import conf
from django_recovery.backends import LocalBackend, S3Backend
from django_recovery.conf import (
    RecoveryConfig,
    build_global_args,
    get_config,
    resolve_binary,
)


def _local(**overrides):
    raw = {
        "BACKEND": "django_recovery.backends.LocalBackend",
        "OPTIONS": {"path": "/tmp/test-repo", "password": "test-password"},
    }
    raw.update(overrides)
    return raw


def test_get_config_defaults_filled():
    config = get_config()
    assert isinstance(config, RecoveryConfig)
    assert isinstance(config.backend, LocalBackend)
    assert config.backend.repository == "/tmp/test-repo"
    assert config.backend.env() == {"RESTIC_PASSWORD": "test-password"}
    assert config.databases == ["default"]
    assert config.media is False
    assert config.tags == ["test"]
    assert config.binary is None


def test_get_config_databases_defaults_when_absent():
    with override_settings(RECOVERY=_local()):
        config = get_config()
    assert config.databases == ["default"]
    assert config.media is False
    assert config.tags == []
    assert config.binary is None


def test_missing_backend_raises():
    with override_settings(RECOVERY={"OPTIONS": {"path": "/tmp/x"}}):
        with pytest.raises(ImproperlyConfigured, match="BACKEND"):
            get_config()


def test_unimportable_backend_raises():
    with override_settings(RECOVERY=_local(BACKEND="django_recovery.backends.Nope")):
        with pytest.raises(ImproperlyConfigured, match="Could not import"):
            get_config()


def test_non_backend_class_raises():
    with override_settings(RECOVERY=_local(BACKEND="django_recovery.conf.get_config")):
        with pytest.raises(ImproperlyConfigured, match="not a BaseBackend subclass"):
            get_config()


def test_unknown_top_level_key_raises():
    with override_settings(RECOVERY=_local(repository="/old/flat/style")):
        with pytest.raises(ImproperlyConfigured, match="Unknown key"):
            get_config()


def test_recovery_missing_entirely_raises():
    with override_settings(RECOVERY=None):
        with pytest.raises(ImproperlyConfigured):
            get_config()


def test_operational_keys_parsed():
    with override_settings(
        RECOVERY=_local(
            DATABASES=["default", "analytics"],
            MEDIA=True,
            TAGS=["prod"],
            BINARY="/opt/restic",
        )
    ):
        config = get_config()
    assert config.databases == ["default", "analytics"]
    assert config.media is True
    assert config.tags == ["prod"]
    assert config.binary == "/opt/restic"


# --- RETENTION / TUNING validation -----------------------------------------

def test_retention_parsed():
    retention = {"daily": 7, "weekly": 4, "within": "7d"}
    with override_settings(RECOVERY=_local(RETENTION=retention)):
        config = get_config()
    assert config.retention == retention


def test_retention_unknown_key_raises():
    with override_settings(RECOVERY=_local(RETENTION={"dayly": 7})):
        with pytest.raises(ImproperlyConfigured, match="dayly"):
            get_config()


@pytest.mark.parametrize("bad", [0, -1, "7", True])
def test_retention_non_positive_int_raises(bad):
    with override_settings(RECOVERY=_local(RETENTION={"daily": bad})):
        with pytest.raises(ImproperlyConfigured, match="positive integer"):
            get_config()


def test_retention_within_must_be_string():
    with override_settings(RECOVERY=_local(RETENTION={"within": 7})):
        with pytest.raises(ImproperlyConfigured, match="duration string"):
            get_config()


def test_tuning_parsed_and_new_keys():
    with override_settings(
        RECOVERY=_local(
            TUNING={"compression": "max", "pack_size": 64},
            HOST="web1",
            SKIP_IF_UNCHANGED=True,
            MEDIA_EXCLUDE=["*.tmp"],
            EXTRA_ARGS=["--insecure-tls"],
        )
    ):
        config = get_config()
    assert config.tuning == {"compression": "max", "pack_size": 64}
    assert config.host == "web1"
    assert config.skip_if_unchanged is True
    assert config.media_exclude == ["*.tmp"]
    assert config.extra_args == ["--insecure-tls"]


def test_tuning_unknown_key_raises():
    with override_settings(RECOVERY=_local(TUNING={"speed": 11})):
        with pytest.raises(ImproperlyConfigured, match="speed"):
            get_config()


def test_tuning_bad_compression_raises():
    with override_settings(RECOVERY=_local(TUNING={"compression": "zstd"})):
        with pytest.raises(ImproperlyConfigured, match="compression"):
            get_config()


def test_tuning_negative_int_raises():
    with override_settings(RECOVERY=_local(TUNING={"pack_size": -1})):
        with pytest.raises(ImproperlyConfigured, match="non-negative"):
            get_config()


# --- build_global_args -------------------------------------------------------

def test_build_global_args_empty_by_default():
    assert build_global_args(_config()) == []


def test_build_global_args_full_tuning():
    config = RecoveryConfig(
        backend=LocalBackend(path="/repo", password="x"),
        databases=["default"],
        tuning={
            "compression": "max",
            "pack_size": 64,
            "limit_upload": 1024,
            "limit_download": 2048,
            "retry_lock": "5m",
            "no_cache": True,
        },
        extra_args=["--verbose"],
    )
    assert build_global_args(config) == [
        "--compression", "max",
        "--pack-size", "64",
        "--limit-upload", "1024",
        "--limit-download", "2048",
        "--retry-lock", "5m",
        "--no-cache",
        "--verbose",
    ]


def test_build_global_args_connections_scoped_to_scheme():
    config = RecoveryConfig(
        backend=S3Backend(
            bucket_name="b", access_key="a", secret_key="s", password="x"
        ),
        databases=["default"],
        tuning={"connections": 8},
    )
    assert build_global_args(config) == ["-o", "s3.connections=8"]


def test_build_global_args_connections_skipped_for_local_path():
    config = RecoveryConfig(
        backend=LocalBackend(path="C:\\backups\\repo", password="x"),
        databases=["default"],
        tuning={"connections": 8},
    )
    # Windows drive letter is not a restic scheme -> no -o emitted.
    assert build_global_args(config) == []


def _config(binary=None):
    return RecoveryConfig(
        backend=LocalBackend(path="/repo", password="x"),
        databases=["default"],
        binary=binary,
    )


def test_resolve_binary_explicit_setting_verbatim(monkeypatch):
    # config.binary is set -> returned as-is, no lookup performed.
    def boom():  # pragma: no cover - should never be called
        raise AssertionError("should not be called")

    monkeypatch.setattr(conf.shutil, "which", lambda name: boom())
    assert resolve_binary(_config(binary="/opt/custom/restic")) == "/opt/custom/restic"


def test_resolve_binary_uses_path(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: "/usr/bin/restic")
    assert resolve_binary(_config()) == "/usr/bin/restic"


def test_resolve_binary_all_fail_raises(monkeypatch):
    monkeypatch.setattr(conf.shutil, "which", lambda name: None)
    with pytest.raises(ImproperlyConfigured):
        resolve_binary(_config())
