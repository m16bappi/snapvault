"""Escape-hatch backend: any restic repository URL, verbatim."""

from __future__ import annotations

from .base import BaseBackend


class GenericBackend(BaseBackend):
    """Pass a raw restic repository URL through unchanged.

    Use for backends without a dedicated class: ``rclone:remote:path``,
    ``rest:https://user:pass@host:8000/``, ``swift:container:/prefix``, etc.
    Extra credential env vars go in the ``extra_env`` option dict.
    """

    # Plain class attribute shadows the base-class ``repository`` property so
    # the option can be assigned directly onto the instance.
    repository = None

    def get_default_options(self) -> dict:
        return {
            "repository": None,
            "extra_env": None,
        }

    def _validate(self) -> None:
        self._require("repository")

    def env(self) -> dict[str, str]:
        return dict(self.extra_env or {})
