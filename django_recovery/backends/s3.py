"""Amazon S3 and S3-compatible repository backend.

Covers AWS S3 plus any S3-compatible service (Cloudflare R2, Backblaze B2,
DigitalOcean Spaces, MinIO, Wasabi, ...) by setting ``endpoint_url``.
"""

from __future__ import annotations

from .base import BaseBackend

DEFAULT_ENDPOINT = "s3.amazonaws.com"


class S3Backend(BaseBackend):
    """Repository at ``s3:<endpoint>/<bucket_name>[/<location>]``."""

    def get_default_options(self) -> dict:
        return {
            "location": "",
            "bucket_name": None,
            "access_key": None,
            "secret_key": None,
            "endpoint_url": None,
            "region_name": None,
            "session_token": None,
        }

    def _validate(self) -> None:
        self._require("bucket_name", "access_key", "secret_key")

    @property
    def repository(self) -> str:
        endpoint = self.endpoint_url or DEFAULT_ENDPOINT
        endpoint = endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
        repo = f"s3:{endpoint}/{self.bucket_name}"
        location = (self.location or "").strip("/")
        return f"{repo}/{location}" if location else repo

    def env(self) -> dict[str, str]:
        env = {
            "AWS_ACCESS_KEY_ID": self.access_key,
            "AWS_SECRET_ACCESS_KEY": self.secret_key,
        }
        if self.region_name:
            env["AWS_DEFAULT_REGION"] = self.region_name
        if self.session_token:
            env["AWS_SESSION_TOKEN"] = self.session_token
        return env
