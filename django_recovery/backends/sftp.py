"""SFTP repository backend.

restic reaches SFTP through the system ``ssh`` binary, so authentication is
key/agent based (``~/.ssh/config``, ssh-agent). Password authentication is
deliberately unsupported — there is no safe way to feed a password to
``ssh`` from here.
"""

from __future__ import annotations

from .base import BaseBackend


class SFTPBackend(BaseBackend):
    """Repository at ``sftp:[<user>@]<host>:[<port>/]<path>``."""

    def get_default_options(self) -> dict:
        return {
            "host": None,
            "path": None,
            "user": None,
            "port": None,
        }

    def _validate(self) -> None:
        self._require("host", "path")

    @property
    def repository(self) -> str:
        host = f"{self.user}@{self.host}" if self.user else self.host
        if self.port:
            return f"sftp://{host}:{self.port}/{str(self.path).lstrip('/')}"
        return f"sftp:{host}:{self.path}"
