"""Google Cloud Storage repository backend."""

from __future__ import annotations

from .base import BaseBackend


class GCSBackend(BaseBackend):
    """Repository at ``gs:<bucket_name>:/[<location>]``.

    Authentication: set ``credentials_file`` to a service-account JSON key
    path. When omitted, restic falls back to Application Default Credentials
    (attached service account on GCE/GKE/Cloud Run) — the recommended
    production setup.
    """

    def get_default_options(self) -> dict:
        return {
            "location": "",
            "bucket_name": None,
            "project_id": None,
            "credentials_file": None,
        }

    def _validate(self) -> None:
        self._require("bucket_name")

    @property
    def repository(self) -> str:
        location = (self.location or "").strip("/")
        return f"gs:{self.bucket_name}:/{location}"

    def env(self) -> dict[str, str]:
        env = {}
        if self.project_id:
            env["GOOGLE_PROJECT_ID"] = self.project_id
        if self.credentials_file:
            env["GOOGLE_APPLICATION_CREDENTIALS"] = str(self.credentials_file)
        return env
