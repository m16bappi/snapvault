"""Local filesystem repository backend."""

from __future__ import annotations

from .base import BaseBackend


class LocalBackend(BaseBackend):
    """Repository in a local directory: ``RECOVERY['OPTIONS']['path']``."""

    def get_default_options(self) -> dict:
        return {"path": None}

    def _validate(self) -> None:
        self._require("path")

    @property
    def repository(self) -> str:
        return str(self.path)
