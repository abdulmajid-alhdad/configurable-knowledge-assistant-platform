"""Minimal server-side Supabase Auth adapter with no browser token exposure."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from knowledge_platform.modules.access_control.domain import AuthenticatedUser


class AuthProviderFailure(RuntimeError):
    """Safe identity-provider failure without retaining provider content."""

    def __init__(self, category: str, status_code: int | None = None) -> None:
        super().__init__("authentication provider operation failed")
        self.category = category
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class AuthSession:
    user: AuthenticatedUser
    access_token: str
    refresh_token: str
    expires_in: int


class SupabaseAuthAdapter:
    """Calls GoTrue through the project's publishable key from the server only."""

    def __init__(self, *, auth_url: str, publishable_key: str, client: Any = None) -> None:
        self._auth_url = auth_url.rstrip("/")
        self._key = publishable_key.strip()
        if not self._auth_url.startswith("https://") or not self._key:
            raise ValueError("Supabase Auth configuration is invalid")
        if client is None:
            httpx = __import__("httpx")
            client = httpx.Client()
        self._client = client

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        headers = {"apikey": self._key, "content-type": "application/json"}
        if access_token is not None:
            headers["authorization"] = f"Bearer {access_token}"
        return headers

    @staticmethod
    def _user(payload: object) -> AuthenticatedUser:
        if not isinstance(payload, dict):
            raise AuthProviderFailure("malformed_response")
        try:
            user_id = UUID(str(payload["id"]))
            email = payload["email"]
            metadata = payload.get("user_metadata")
            display_name = metadata.get("display_name") if isinstance(metadata, dict) else None
        except (KeyError, TypeError, ValueError):
            raise AuthProviderFailure("malformed_response") from None
        if not isinstance(email, str):
            raise AuthProviderFailure("malformed_response")
        return AuthenticatedUser(
            id=user_id,
            email=email,
            display_name=display_name if isinstance(display_name, str) else None,
        )

    def _session(self, response: Any) -> AuthSession:
        if response.status_code >= 400:
            raise AuthProviderFailure("http_status", response.status_code)
        try:
            payload = response.json()
            return AuthSession(
                user=self._user(payload["user"]),
                access_token=str(payload["access_token"]),
                refresh_token=str(payload["refresh_token"]),
                expires_in=int(payload["expires_in"]),
            )
        except AuthProviderFailure:
            raise
        except (KeyError, TypeError, ValueError):
            raise AuthProviderFailure("malformed_response") from None

    def sign_in(self, *, email: str, password: str) -> AuthSession:
        try:
            response = self._client.post(
                f"{self._auth_url}/token?grant_type=password",
                headers=self._headers(),
                json={"email": email.strip().casefold(), "password": password},
                timeout=15,
            )
        except Exception:
            raise AuthProviderFailure("connection") from None
        return self._session(response)

    def refresh(self, refresh_token: str) -> AuthSession:
        try:
            response = self._client.post(
                f"{self._auth_url}/token?grant_type=refresh_token",
                headers=self._headers(),
                json={"refresh_token": refresh_token},
                timeout=15,
            )
        except Exception:
            raise AuthProviderFailure("connection") from None
        return self._session(response)

    def get_user(self, access_token: str) -> AuthenticatedUser:
        try:
            response = self._client.get(
                f"{self._auth_url}/user",
                headers=self._headers(access_token),
                timeout=10,
            )
        except Exception:
            raise AuthProviderFailure("connection") from None
        if response.status_code >= 400:
            raise AuthProviderFailure("http_status", response.status_code)
        try:
            return self._user(response.json())
        except AuthProviderFailure:
            raise
        except Exception:
            raise AuthProviderFailure("malformed_response") from None

    def sign_out(self, access_token: str) -> None:
        try:
            response = self._client.post(
                f"{self._auth_url}/logout",
                headers=self._headers(access_token),
                timeout=10,
            )
        except Exception:
            raise AuthProviderFailure("connection") from None
        if response.status_code >= 400:
            raise AuthProviderFailure("http_status", response.status_code)
