from uuid import uuid4

import pytest

from knowledge_platform.infrastructure.auth.api_keys import ApiKeyPrincipal


def test_api_key_principal_is_not_a_user_and_requires_explicit_scope() -> None:
    principal = ApiKeyPrincipal(
        key_id=uuid4(),
        workspace_id=uuid4(),
        scopes=("usage.read",),
        created_by=uuid4(),
    )

    assert principal.allows("usage.read")
    assert not principal.allows("workspace.manage")
    principal.require("usage.read")
    with pytest.raises(PermissionError, match="API_KEY_SCOPE_DENIED"):
        principal.require("workspace.manage")


def test_api_key_principal_has_no_supabase_user_identity_field() -> None:
    assert "user_id" not in ApiKeyPrincipal.__dataclass_fields__
