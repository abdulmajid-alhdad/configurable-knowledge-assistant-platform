"""SQLAlchemy adapter for commercial and advanced administration.

The module models internal commercial state only. Payment collection and
provider-backed billing remain future ports. Secret values never cross this
boundary except for a newly generated workspace API key returned once.
"""

import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.commercial import CommercialError
from knowledge_platform.infrastructure.persistence.access_control import (
    AccessControlService,
)
from knowledge_platform.modules.access_control.domain import (
    Permission,
    PermissionScope,
    permission_codes_for_scope,
)


class CommercialService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
        self._access = AccessControlService(sessions)

    @contextmanager
    def _tx(self, user_id: UUID, workspace_id: UUID) -> Iterator[Session]:
        with self._sessions.begin() as session:
            session.execute(
                text("select set_config('app.user_id', :v, true)"), {"v": str(user_id)}
            )
            session.execute(
                text("select set_config('app.workspace_id', :v, true)"),
                {"v": str(workspace_id)},
            )
            yield session

    @staticmethod
    def check_count_limit(
        session: Session, workspace_id: UUID, key: str, current_count: int
    ) -> str | None:
        """Lock subscription state and return a stable denial or ``None``.

        The subscription-row lock is held by the caller through its mutation,
        serializing concurrent count-based creation attempts.
        """
        value = session.execute(
            text("select platform.check_workspace_entitlement(:w,:key,:count)"),
            {"w": workspace_id, "key": key, "count": current_count},
        ).scalar_one()
        return str(value) if value else None

    @staticmethod
    def append_audit(
        session: Session,
        workspace_id: UUID,
        action: str,
        resource_type: str,
        *,
        outcome: str = "succeeded",
        resource_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        session.execute(
            text("""
                select platform.append_audit_event(
                  :workspace,:action,:resource_type,:resource_id,:outcome,'',
                  cast(:metadata as jsonb))
            """),
            {
                "workspace": workspace_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "outcome": outcome,
                "metadata": json.dumps(metadata or {}, separators=(",", ":")),
            },
        )

    def plans(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.PLANS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(text("""
                select id,code,name,description,status,billing_interval,price_amount,currency
                from platform.plans where status='active' order by code
            """)).mappings().all()
        return [dict(row) for row in rows]

    def subscription(self, user_id: UUID, workspace_id: UUID) -> dict[str, object]:
        self._access.require_system(user_id, Permission.SUBSCRIPTIONS_READ)
        with self._tx(user_id, workspace_id) as session:
            row = session.execute(text("""
                select subscription.workspace_id, subscription.state,
                       subscription.starts_at, subscription.ends_at,
                       subscription.billing_contact, plan.code plan_code,
                       plan.name plan_name
                from platform.workspace_subscriptions subscription
                join platform.plans plan on plan.id=subscription.plan_id
                where subscription.workspace_id=:workspace
            """), {"workspace": workspace_id}).mappings().one_or_none()
        if row is None:
            raise CommercialError("SUBSCRIPTION_NOT_FOUND")
        return dict(row)

    def update_subscription(
        self, user_id: UUID, workspace_id: UUID, plan_code: str, state: str
    ) -> None:
        self._access.require_system(user_id, Permission.SUBSCRIPTIONS_MANAGE)
        if state not in {"active", "trialing", "past_due", "suspended", "cancelled"}:
            raise CommercialError("SUBSCRIPTION_STATE_INVALID")
        with self._tx(user_id, workspace_id) as session:
            changed = session.execute(
                text("select platform.update_workspace_subscription(:w,:p,:s)"),
                {"w": workspace_id, "p": plan_code, "s": state},
            ).scalar_one()
            if not changed:
                raise CommercialError("PLAN_NOT_FOUND")
            self.append_audit(
                session, workspace_id, "subscription.updated", "subscription",
                metadata={"plan_code": plan_code, "state": state},
            )

    def entitlements(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.SUBSCRIPTIONS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(text("""
                select entitlement.entitlement_key, entitlement.limit_value,
                       entitlement.unit, subscription.state,
                       entitlement.limit_value is null as unlimited,
                       subscription.state in ('active','trialing') as mutations_allowed
                from platform.workspace_subscriptions subscription
                join platform.plan_entitlements entitlement
                  on entitlement.plan_id=subscription.plan_id
                where subscription.workspace_id=:workspace
                order by entitlement.entitlement_key
            """), {"workspace": workspace_id}).mappings().all()
        return [dict(row) for row in rows]

    def require_count_limit(
        self, user_id: UUID, workspace_id: UUID, key: str, current_count: int
    ) -> None:
        """Compatibility entrypoint for callers without an existing session."""
        self._access.require(user_id, workspace_id, Permission.WORKSPACE_READ)
        with self._tx(user_id, workspace_id) as session:
            denial = self.check_count_limit(session, workspace_id, key, current_count)
        if denial:
            raise CommercialError(denial)

    def providers(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.PROVIDERS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(text("""
                select provider.code,provider.display_name,provider.provider_type,
                       provider.base_url default_base_url,
                       setting.base_url_override,
                       coalesce(setting.base_url_override,provider.base_url) base_url,
                       setting.enabled,setting.administrative_status,setting.updated_at
                from platform.provider_registry provider
                join platform.workspace_provider_settings setting
                  on setting.provider_code=provider.code
                 and setting.workspace_id=:workspace
                order by provider.code
            """), {"workspace": workspace_id}).mappings().all()
        return [dict(row) for row in rows]

    def update_provider(
        self, user_id: UUID, workspace_id: UUID, provider_code: str, *,
        enabled: bool, administrative_status: str, base_url_override: str | None,
    ) -> None:
        self._access.require_system(user_id, Permission.PROVIDERS_MANAGE)
        if administrative_status not in {"configured", "disabled", "degraded"}:
            raise CommercialError("PROVIDER_STATUS_INVALID")
        if base_url_override is not None and not base_url_override.startswith("https://"):
            raise CommercialError("PROVIDER_BASE_URL_INVALID")
        with self._tx(user_id, workspace_id) as session:
            changed = session.execute(
                text("select platform.update_workspace_provider(:w,:code,:enabled,:status,:url)"),
                {"w": workspace_id, "code": provider_code, "enabled": enabled,
                 "status": administrative_status, "url": base_url_override},
            ).scalar_one()
            if not changed:
                raise CommercialError("PROVIDER_NOT_FOUND")
            self.append_audit(
                session, workspace_id, "provider.updated", "provider",
                metadata={"provider_code": provider_code, "enabled": enabled,
                          "administrative_status": administrative_status},
            )

    def credentials(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.CREDENTIALS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(text("""
                select id,workspace_id,name,provider_code,status,created_at,updated_at,
                       reference_type
                from platform.list_credential_references(:workspace)
            """), {"workspace": workspace_id}).mappings().all()
        return [dict(row) for row in rows]

    def save_credential_reference(
        self, user_id: UUID, workspace_id: UUID, *, name: str,
        provider_code: str | None, secret_reference: str, status: str,
    ) -> UUID:
        self._access.require_system(user_id, Permission.CREDENTIALS_MANAGE)
        if re.fullmatch(
            r"(?:env:[A-Z][A-Z0-9_]{1,79}|vault:[A-Za-z0-9_./-]{1,180})",
            secret_reference,
        ) is None:
            raise CommercialError("CREDENTIAL_REFERENCE_INVALID")
        if status not in {"configured", "disabled", "invalid"}:
            raise CommercialError("CREDENTIAL_STATUS_INVALID")
        with self._tx(user_id, workspace_id) as session:
            reference_id = cast(
                UUID,
                session.execute(
                    text(
                        "select platform.save_credential_reference"
                        "(:w,:name,:provider,:reference,:status)"
                    ),
                    {"w": workspace_id, "name": name, "provider": provider_code,
                     "reference": secret_reference, "status": status},
                ).scalar_one(),
            )
            self.append_audit(
                session, workspace_id, "credential_reference.saved",
                "credential_reference", resource_id=reference_id,
                metadata={"name": name, "provider_code": provider_code, "status": status},
            )
        return reference_id

    def delete_credential_reference(
        self, user_id: UUID, workspace_id: UUID, reference_id: UUID
    ) -> None:
        self._access.require_system(user_id, Permission.CREDENTIALS_MANAGE)
        with self._tx(user_id, workspace_id) as session:
            changed = session.execute(
                text("select platform.delete_credential_reference(:w,:id)"),
                {"w": workspace_id, "id": reference_id},
            ).scalar_one()
            if not changed:
                raise CommercialError("CREDENTIAL_REFERENCE_NOT_FOUND")
            self.append_audit(
                session, workspace_id, "credential_reference.deleted",
                "credential_reference", resource_id=reference_id,
            )

    def security(self, user_id: UUID, workspace_id: UUID) -> dict[str, object]:
        self._access.require_system(user_id, Permission.SECURITY_READ)
        with self._tx(user_id, workspace_id) as session:
            row = session.execute(text("""
                select api_keys_enabled,invitations_enabled,
                       max_invitation_expiry_days,updated_at
                from platform.workspace_security_settings where workspace_id=:workspace
            """), {"workspace": workspace_id}).mappings().one()
        return dict(row)

    def settings(self, user_id: UUID, workspace_id: UUID) -> dict[str, object]:
        self._access.require_system(user_id, Permission.SETTINGS_READ)
        with self._tx(user_id, workspace_id) as session:
            row = session.execute(text("""
                select display_name,locale,timezone,commercial_contact,updated_at
                from platform.workspace_settings where workspace_id=:workspace
            """), {"workspace": workspace_id}).mappings().one()
        return dict(row)

    def api_keys(self, user_id: UUID, workspace_id: UUID) -> list[dict[str, object]]:
        self._access.require_system(user_id, Permission.API_KEYS_READ)
        with self._tx(user_id, workspace_id) as session:
            rows = session.execute(text("""
                select id,name,key_prefix,scopes,created_at,last_used_at,expires_at,revoked_at
                from platform.workspace_api_keys where workspace_id=:workspace
                order by created_at desc
            """), {"workspace": workspace_id}).mappings().all()
        return [dict(row) for row in rows]

    def create_api_key(
        self, user_id: UUID, workspace_id: UUID, name: str,
        scopes: list[str], expires_at: datetime | None = None,
    ) -> dict[str, object]:
        self._access.require_system(user_id, Permission.API_KEYS_MANAGE)
        allowed_scopes = permission_codes_for_scope(
            PermissionScope.WORKSPACE, delegable_only=True
        )
        if not scopes or any(scope not in allowed_scopes for scope in scopes):
            raise CommercialError("API_KEY_SCOPE_INVALID")
        candidate_expiry = expires_at
        if candidate_expiry is not None:
            if candidate_expiry.tzinfo is None:
                candidate_expiry = candidate_expiry.replace(tzinfo=UTC)
            if candidate_expiry <= datetime.now(UTC):
                raise CommercialError("API_KEY_EXPIRY_INVALID")
        for scope in scopes:
            self._access.require(user_id, workspace_id, Permission(scope))

        denial: str | None = None
        created: dict[str, object] | None = None
        with self._tx(user_id, workspace_id) as session:
            denial_value = session.execute(
                text("select platform.check_api_key_creation(:w)"), {"w": workspace_id}
            ).scalar_one()
            denial = str(denial_value) if denial_value else None
            if denial:
                self.append_audit(
                    session, workspace_id, "api_key.create_denied", "api_key",
                    outcome="denied", metadata={"reason": denial},
                )
            else:
                raw = "kp_" + secrets.token_hex(32)
                digest = hashlib.sha256(raw.encode()).hexdigest()
                prefix = raw[:11]
                fingerprint = digest[:32]
                key_id = session.execute(text("""
                    select platform.create_workspace_api_key(
                      :workspace,:name,:prefix,:fingerprint,:hash,
                      cast(:scopes as text[]),:expires_at)
                """), {"workspace": workspace_id, "name": name, "prefix": prefix,
                        "fingerprint": fingerprint, "hash": digest,
                        "scopes": "{" + ",".join(scopes) + "}",
                        "expires_at": candidate_expiry}).scalar_one()
                self.append_audit(
                    session, workspace_id, "api_key.created", "api_key",
                    resource_id=key_id, metadata={"name": name, "prefix": prefix},
                )
                created = {"id": key_id, "name": name, "prefix": prefix,
                           "secret": raw, "created_at": datetime.now(UTC)}
        if denial:
            raise CommercialError(denial)
        if created is None:
            raise CommercialError("API_KEY_CREATION_FAILED")
        return created

    def revoke_api_key(self, user_id: UUID, workspace_id: UUID, key_id: UUID) -> None:
        self._access.require_system(user_id, Permission.API_KEYS_MANAGE)
        with self._tx(user_id, workspace_id) as session:
            changed = session.execute(
                text("select platform.revoke_workspace_api_key(:workspace,:key)"),
                {"workspace": workspace_id, "key": key_id},
            ).scalar_one()
            if not changed:
                raise CommercialError("API_KEY_NOT_FOUND")
            self.append_audit(
                session, workspace_id, "api_key.revoked", "api_key", resource_id=key_id
            )

    def authenticate_api_key(self, plaintext: str) -> dict[str, object] | None:
        if not plaintext.startswith("kp_") or len(plaintext) != 67:
            return None
        candidate_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        candidate_fingerprint = candidate_hash[:32]
        with self._sessions.begin() as session:
            row = session.execute(
                text("select * from platform.lookup_workspace_api_key(:fingerprint)"),
                {"fingerprint": candidate_fingerprint},
            ).mappings().one_or_none()
            if row is None or not hmac.compare_digest(str(row["secret_hash"]), candidate_hash):
                return None
            session.execute(
                text("select platform.touch_workspace_api_key(:key_id)"),
                {"key_id": row["key_id"]},
            )
            result = dict(row)
            result.pop("secret_hash", None)
            return result

    def update_security(
        self, user_id: UUID, workspace_id: UUID, *, api_keys_enabled: bool,
        invitations_enabled: bool, max_invitation_expiry_days: int,
    ) -> None:
        self._access.require_system(user_id, Permission.SECURITY_MANAGE)
        with self._tx(user_id, workspace_id) as session:
            session.execute(
                text("select platform.update_workspace_security(:w,:k,:i,:d)"),
                {"w": workspace_id, "k": api_keys_enabled, "i": invitations_enabled,
                 "d": max_invitation_expiry_days},
            )
            self.append_audit(
                session, workspace_id, "security.updated", "security_settings",
                metadata={"api_keys_enabled": api_keys_enabled,
                          "invitations_enabled": invitations_enabled,
                          "max_invitation_expiry_days": max_invitation_expiry_days},
            )

    def update_settings(
        self, user_id: UUID, workspace_id: UUID, *, display_name: str | None,
        locale: str, timezone: str, commercial_contact: str | None,
    ) -> None:
        self._access.require_system(user_id, Permission.WORKSPACE_SETTINGS_MANAGE)
        with self._tx(user_id, workspace_id) as session:
            session.execute(
                text("select platform.update_workspace_settings(:w,:n,:l,:t,:c)"),
                {"w": workspace_id, "n": display_name, "l": locale,
                 "t": timezone, "c": commercial_contact},
            )
            self.append_audit(
                session, workspace_id, "workspace_settings.updated", "workspace_settings"
            )
