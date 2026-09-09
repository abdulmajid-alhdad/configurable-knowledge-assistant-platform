from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from knowledge_platform.application.identity_provisioning import (
    ActivationPreview,
    ActivationResult,
    IdentityAdminFailure,
    IdentityProvisioningFailure,
    IdentityProvisioningService,
    ProvisionedIdentity,
)
from knowledge_platform.modules.access_control.domain import Permission


class FakeAccess:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, Permission]] = []

    def require_system(self, actor: UUID, permission: Permission) -> None:
        self.calls.append((actor, permission))


class FakeIdentityAdmin:
    def __init__(self) -> None:
        self.identity = ProvisionedIdentity(uuid4(), "new@example.com")
        self.events: list[str] = []
        self.fail_delete = False

    def create_unconfirmed_user(
        self, *, email: str, password: str, display_name: str
    ) -> ProvisionedIdentity:
        assert email == self.identity.email
        assert password
        assert display_name == "مستخدم جديد"
        self.events.append("create_unconfirmed")
        return self.identity

    def confirm_user(self, user_id: UUID) -> None:
        assert user_id == self.identity.id
        self.events.append("confirm")

    def delete_user(self, user_id: UUID) -> None:
        assert user_id == self.identity.id
        self.events.append("delete")
        if self.fail_delete:
            raise IdentityAdminFailure("IDENTITY_PROVIDER_FAILURE")


class FakeStore:
    def __init__(self, identity: ProvisionedIdentity) -> None:
        self.identity = identity
        self.events: list[str] = []
        self.digest: str | None = None
        self.fail_create = False
        self.preview_error: str | None = None

    def validate(self, actor: UUID, intent: object) -> None:
        del actor, intent
        self.events.append("validate")

    def create(
        self, actor: UUID, identity: ProvisionedIdentity, intent: object, token_digest: str
    ) -> dict[str, object]:
        del actor, intent
        assert identity == self.identity
        self.events.append("persist")
        self.digest = token_digest
        if self.fail_create:
            raise RuntimeError("database rejected")
        now = datetime.now(UTC)
        return {
            "created_invitation_id": uuid4(),
            "created_workspace_id": uuid4(),
            "created_user_id": identity.id,
            "created_team_id": None,
            "created_status": "pending",
            "created_at": now,
            "expires_at": now + timedelta(days=7),
        }

    def preview(self, token_digest: str) -> ActivationPreview:
        self.events.append("preview")
        self.digest = token_digest
        return ActivationPreview(
            invitation_id=uuid4(),
            provisioned_user_id=self.identity.id,
            email=self.identity.email,
            display_name="مستخدم جديد",
            workspace_id=uuid4(),
            workspace_name="مساحة العمل",
            role_id=uuid4(),
            role_name="MEMBER",
            team_id=None,
            team_name=None,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            error_code=self.preview_error,
        )

    def activate(self, token_digest: str, user_id: UUID) -> ActivationResult:
        assert token_digest == self.digest
        assert user_id == self.identity.id
        self.events.append("activate")
        return ActivationResult(uuid4(), user_id, None, None)


def service() -> tuple[IdentityProvisioningService, FakeAccess, FakeIdentityAdmin, FakeStore]:
    access = FakeAccess()
    identity = FakeIdentityAdmin()
    store = FakeStore(identity.identity)
    return (
        IdentityProvisioningService(
            access=access,  # type: ignore[arg-type]
            identity_admin=identity,
            store=store,
        ),
        access,
        identity,
        store,
    )


def test_provisioning_validates_before_auth_and_persists_only_digest() -> None:
    subject, access, identity, store = service()
    actor, workspace, role = uuid4(), uuid4(), uuid4()

    result = subject.provision(
        actor,
        display_name=" مستخدم جديد ",
        email="New@Example.com",
        password="a-safe-initial-password",
        workspace_id=workspace,
        role_id=role,
        team_id=None,
        expires_in_days=7,
    )

    assert access.calls == [(actor, Permission.INVITATIONS_MANAGE)]
    assert store.events == ["validate", "persist"]
    assert identity.events == ["create_unconfirmed"]
    assert store.digest is not None and len(store.digest) == 64
    assert store.digest not in result.activation_path
    assert result.activation_path.startswith("/app/invitations/accept#token=")


def test_platform_failure_compensates_new_auth_identity() -> None:
    subject, _, identity, store = service()
    store.fail_create = True

    with pytest.raises(IdentityProvisioningFailure, match="PLATFORM_PERSISTENCE_FAILED"):
        subject.provision(
            uuid4(),
            display_name="مستخدم جديد",
            email="new@example.com",
            password="a-safe-initial-password",
            workspace_id=uuid4(),
            role_id=uuid4(),
            team_id=None,
            expires_in_days=7,
        )

    assert identity.events == ["create_unconfirmed", "delete"]


def test_preview_never_confirms_or_consumes_invitation() -> None:
    subject, _, identity, store = service()

    result = subject.preview("a" * 43)

    assert result.status == "pending"
    assert identity.events == []
    assert store.events == ["preview"]


def test_activation_confirms_identity_then_atomically_activates_platform_state() -> None:
    subject, _, identity, store = service()

    result = subject.activate("b" * 43)

    assert result.user_id == identity.identity.id
    assert identity.events == ["confirm"]
    assert store.events == ["preview", "activate"]


def test_replay_state_is_rejected_before_identity_admin_call() -> None:
    subject, _, identity, store = service()
    store.preview_error = "INVITATION_ALREADY_ACCEPTED"

    with pytest.raises(
        IdentityProvisioningFailure, match="INVITATION_ALREADY_ACCEPTED"
    ):
        subject.activate("c" * 43)

    assert identity.events == []
    assert store.events == ["preview"]
