"""Settings parsing/validation and restic binary resolution.

``settings.RECOVERY`` follows the Django ``STORAGES`` shape: a ``BACKEND``
dotted path to a :class:`~django_recovery.backends.base.BaseBackend`
subclass plus an ``OPTIONS`` dict passed to it as keyword arguments. The
backend builds the restic repository URL and the credential environment;
operational keys (``DATABASES``, ``MEDIA``, ``TAGS``, ``BINARY``) stay
top-level.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from .backends.base import BaseBackend

_KNOWN_KEYS = {
    "BACKEND",
    "OPTIONS",
    "DATABASES",
    "MEDIA",
    "TAGS",
    "BINARY",
    "RETENTION",
    "TUNING",
    "HOST",
    "SKIP_IF_UNCHANGED",
    "MEDIA_EXCLUDE",
    "EXTRA_ARGS",
}

# --keep-* units accepted in RECOVERY["RETENTION"]; "within" takes a restic
# duration string ("2y5m7d3h"), the rest take positive snapshot counts.
_RETENTION_KEYS = {"last", "hourly", "daily", "weekly", "monthly", "yearly", "within"}

_TUNING_KEYS = {
    "compression",
    "pack_size",
    "read_concurrency",
    "limit_upload",
    "limit_download",
    "retry_lock",
    "cache_dir",
    "no_cache",
    "connections",
}

_COMPRESSION_MODES = {"auto", "off", "fastest", "better", "max"}


@dataclass(frozen=True)
class RecoveryConfig:
    """Validated view of ``settings.RECOVERY``."""

    backend: BaseBackend
    databases: list[str]
    media: bool = False
    tags: list[str] = field(default_factory=list)
    binary: str | None = None
    retention: dict = field(default_factory=dict)
    tuning: dict = field(default_factory=dict)
    host: str | None = None
    skip_if_unchanged: bool = False
    media_exclude: list[str] = field(default_factory=list)
    extra_args: list[str] = field(default_factory=list)


def _validate_retention(raw: dict) -> dict:
    unknown = set(raw) - _RETENTION_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown key(s) in RECOVERY['RETENTION']: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_RETENTION_KEYS))}."
        )
    for key, value in raw.items():
        if key == "within":
            if not isinstance(value, str) or not value:
                raise ImproperlyConfigured(
                    "RECOVERY['RETENTION']['within'] must be a non-empty restic "
                    "duration string, e.g. '7d' or '2y5m7d3h'."
                )
        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ImproperlyConfigured(
                f"RECOVERY['RETENTION'][{key!r}] must be a positive integer."
            )
    return dict(raw)


def _validate_tuning(raw: dict) -> dict:
    unknown = set(raw) - _TUNING_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown key(s) in RECOVERY['TUNING']: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_TUNING_KEYS))}."
        )
    compression = raw.get("compression")
    if compression is not None and compression not in _COMPRESSION_MODES:
        raise ImproperlyConfigured(
            f"RECOVERY['TUNING']['compression'] must be one of "
            f"{', '.join(sorted(_COMPRESSION_MODES))}; got {compression!r}."
        )
    for key in ("pack_size", "read_concurrency", "limit_upload", "limit_download",
                "connections"):
        value = raw.get(key)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ImproperlyConfigured(
                f"RECOVERY['TUNING'][{key!r}] must be a non-negative integer."
            )
    return dict(raw)


def get_config() -> RecoveryConfig:
    """Read and validate ``settings.RECOVERY`` into a :class:`RecoveryConfig`.

    Raises:
        ImproperlyConfigured: if ``RECOVERY`` is absent, ``BACKEND`` is
            missing, the backend class cannot be imported or is not a
            ``BaseBackend`` subclass, or the backend rejects ``OPTIONS``.
    """
    raw = getattr(settings, "RECOVERY", None)
    if not raw:
        raise ImproperlyConfigured(
            "settings.RECOVERY is required to use django-recovery."
        )

    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown key(s) in settings.RECOVERY: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_KNOWN_KEYS))}."
        )

    backend_path = raw.get("BACKEND")
    if not backend_path:
        raise ImproperlyConfigured(
            "settings.RECOVERY['BACKEND'] is required, e.g. "
            "'django_recovery.backends.LocalBackend'."
        )

    try:
        backend_cls = import_string(backend_path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"Could not import RECOVERY['BACKEND'] {backend_path!r}: {exc}"
        ) from exc
    if not (isinstance(backend_cls, type) and issubclass(backend_cls, BaseBackend)):
        raise ImproperlyConfigured(
            f"RECOVERY['BACKEND'] {backend_path!r} is not a BaseBackend subclass."
        )

    options = raw.get("OPTIONS") or {}
    backend = backend_cls(**options)

    databases = raw.get("DATABASES") or ["default"]

    return RecoveryConfig(
        backend=backend,
        databases=list(databases),
        media=bool(raw.get("MEDIA", False)),
        tags=list(raw.get("TAGS") or []),
        binary=raw.get("BINARY"),
        retention=_validate_retention(raw.get("RETENTION") or {}),
        tuning=_validate_tuning(raw.get("TUNING") or {}),
        host=raw.get("HOST"),
        skip_if_unchanged=bool(raw.get("SKIP_IF_UNCHANGED", False)),
        media_exclude=list(raw.get("MEDIA_EXCLUDE") or []),
        extra_args=list(raw.get("EXTRA_ARGS") or []),
    )


# Repository URL schemes restic accepts; used to scope -o <scheme>.connections.
_REPO_SCHEMES = {"s3", "gs", "azure", "sftp", "rest", "rclone", "swift", "b2", "local"}


def build_global_args(config: RecoveryConfig) -> list[str]:
    """Translate ``RECOVERY['TUNING']`` + ``EXTRA_ARGS`` into restic global flags.

    Applied to every restic invocation. ``read_concurrency`` is deliberately
    absent here — it is a ``backup``-only flag and is passed per-call by the
    service layer.
    """
    tuning = config.tuning
    args: list[str] = []
    if tuning.get("compression"):
        args += ["--compression", tuning["compression"]]
    if tuning.get("pack_size"):
        args += ["--pack-size", str(tuning["pack_size"])]
    if tuning.get("limit_upload"):
        args += ["--limit-upload", str(tuning["limit_upload"])]
    if tuning.get("limit_download"):
        args += ["--limit-download", str(tuning["limit_download"])]
    if tuning.get("retry_lock"):
        args += ["--retry-lock", str(tuning["retry_lock"])]
    if tuning.get("cache_dir"):
        args += ["--cache-dir", str(tuning["cache_dir"])]
    if tuning.get("no_cache"):
        args += ["--no-cache"]
    if tuning.get("connections"):
        scheme = config.backend.repository.split(":", 1)[0]
        if scheme in _REPO_SCHEMES:
            args += ["-o", f"{scheme}.connections={tuning['connections']}"]
        # bare local paths (incl. Windows drive letters) have no scheme to scope
        # the option to; restic's local backend ignores it anyway.
    args += config.extra_args
    return args


def resolve_binary(config: RecoveryConfig) -> str:
    """Resolve the path to the restic binary.

    Resolution order:
        1. ``config.binary`` if explicitly set (returned verbatim).
        2. ``shutil.which("restic")`` on ``PATH``.
        3. Otherwise raise :class:`ImproperlyConfigured`.

    restic must be installed on the system (see the project README);
    django-recovery does not bundle a binary.
    """
    if config.binary:
        return config.binary

    found = shutil.which("restic")
    if found:
        return found

    raise ImproperlyConfigured(
        "Could not locate a restic binary. Install restic and place it on your "
        "PATH, or set RECOVERY['BINARY'] to an explicit path."
    )
