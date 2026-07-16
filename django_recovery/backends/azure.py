"""Microsoft Azure Blob Storage repository backend."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import BaseBackend


class AzureBackend(BaseBackend):
    """Repository at ``azure:<container>:/[<location>]``.

    Authentication: exactly one of ``account_key`` or ``sas_token``.
    """

    def get_default_options(self) -> dict:
        return {
            "location": "",
            "container": None,
            "account_name": None,
            "account_key": None,
            "sas_token": None,
        }

    def _validate(self) -> None:
        self._require("container", "account_name")
        if bool(self.account_key) == bool(self.sas_token):
            raise ImproperlyConfigured(
                "AzureBackend requires exactly one of 'account_key' or "
                "'sas_token' in RECOVERY['OPTIONS']."
            )

    @property
    def repository(self) -> str:
        location = (self.location or "").strip("/")
        return f"azure:{self.container}:/{location}"

    def env(self) -> dict[str, str]:
        env = {"AZURE_ACCOUNT_NAME": self.account_name}
        if self.account_key:
            env["AZURE_ACCOUNT_KEY"] = self.account_key
        else:
            env["AZURE_ACCOUNT_SAS"] = self.sas_token
        return env
