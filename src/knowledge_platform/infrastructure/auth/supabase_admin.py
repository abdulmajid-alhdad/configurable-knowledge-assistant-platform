"""Server-only Supabase Auth administrative adapter."""

from typing import Any
from uuid import UUID

from knowledge_platform.application.identity_provisioning import (
    IdentityAdminFailure,
    ProvisionedIdentity,
)


class SupabaseIdentityAdminAdapter:
    """Uses a backend secret solely against Supabase Auth Admin endpoints."""

    def __init__(
        self, *, auth_url: str, admin_secret: str | None, client: Any = None
    ) -> None:
        self._auth_url = auth_url.rstrip("/")
        self._secret = (admin_secret or "").strip()
        if not self._auth_url.startswith("https://"):
            raise ValueError("Supabase Auth administration URL is invalid")
        if client is None:
            httpx = __import__("httpx")
            client = httpx.Client()
        self._client = client

    def _headers(self) -> dict[str, str]:
        if not self._secret:
            raise IdentityAdminFailure("IDENTITY_ADMIN_NOT_CONFIGURED")
        return {
            "apikey": self._secret,
            "authorization": f"Bearer {self._secret}",
            "content-type": "application/json",
        }

    @staticmethod
    def _failure(response: Any) -> IdentityAdminFailure:
        code = ""
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("code"), str):
                code = payload["code"]
        except Exception:
            pass
        if response.status_code == 409 or code in {
            "email_exists",
            "user_already_exists",
        }:
            return IdentityAdminFailure("IDENTITY_ALREADY_EXISTS")
        if response.status_code == 422:
            return IdentityAdminFailure("IDENTITY_INPUT_REJECTED")
        if response.status_code == 404:
            return IdentityAdminFailure("PROVISIONED_IDENTITY_MISSING")
        return IdentityAdminFailure("IDENTITY_PROVIDER_FAILURE")

    def create_unconfirmed_user(
        self, *, email: str, password: str, display_name: str
    ) -> ProvisionedIdentity:
        try:
            response = self._client.post(
                f"{self._auth_url}/admin/users",
                headers=self._headers(),
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": False,
                    "user_metadata": {"display_name": display_name},
                },
                timeout=15,
            )
        except IdentityAdminFailure:
            raise
        except Exception:
            raise IdentityAdminFailure("IDENTITY_PROVIDER_FAILURE") from None
        if response.status_code >= 400:
            raise self._failure(response)
        try:
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("user"), dict):
                payload = payload["user"]
            identity_id = UUID(str(payload["id"]))
            response_email = str(payload["email"]).strip().casefold()
        except (KeyError, TypeError, ValueError):
            raise IdentityAdminFailure("IDENTITY_PROVIDER_MALFORMED") from None
        if response_email != email:
            raise IdentityAdminFailure("IDENTITY_PROVIDER_MALFORMED")
        return ProvisionedIdentity(id=identity_id, email=response_email)

    def confirm_user(self, user_id: UUID) -> None:
        try:
            response = self._client.put(
                f"{self._auth_url}/admin/users/{user_id}",
                headers=self._headers(),
                json={"email_confirm": True},
                timeout=15,
            )
        except IdentityAdminFailure:
            raise
        except Exception:
            raise IdentityAdminFailure("IDENTITY_PROVIDER_FAILURE") from None
        if response.status_code >= 400:
            raise self._failure(response)

    def delete_user(self, user_id: UUID) -> None:
        try:
            response = self._client.delete(
                f"{self._auth_url}/admin/users/{user_id}",
                headers=self._headers(),
                timeout=15,
            )
        except IdentityAdminFailure:
            raise
        except Exception:
            raise IdentityAdminFailure("IDENTITY_PROVIDER_FAILURE") from None
        if response.status_code >= 400 and response.status_code != 404:
            raise self._failure(response)
