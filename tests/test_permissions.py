from app.core.permissions import (
    ALL_SCOPES,
    ROLE_SCOPES,
    has_scope,
)


EXPECTED_ANALYST_SCOPES = frozenset(
    {
        "lotteries:read",
        "draws:read",
        "predictions:read",
        "predictions:generate",
        "analytics:read",
        "crypto:use",
    }
)


def test_all_scopes_are_canonical_and_admin_has_all():
    assert len(ALL_SCOPES) == 10
    assert ROLE_SCOPES["admin"] == ALL_SCOPES
    assert all(has_scope("admin", scope) for scope in ALL_SCOPES)


def test_analyst_has_exactly_the_expected_scopes():
    assert ROLE_SCOPES["analyst"] == EXPECTED_ANALYST_SCOPES
    assert all(has_scope("analyst", scope) for scope in EXPECTED_ANALYST_SCOPES)
    assert not has_scope("analyst", "lotteries:write")
    assert not has_scope("analyst", "draws:write")
    assert not has_scope("analyst", "tenant:manage")
    assert not has_scope("analyst", "memberships:manage")


def test_viewer_and_service_have_no_scopes():
    assert ROLE_SCOPES["viewer"] == frozenset()
    assert ROLE_SCOPES["service"] == frozenset()
    assert not any(has_scope("viewer", scope) for scope in ALL_SCOPES)
    assert not any(has_scope("service", scope) for scope in ALL_SCOPES)


def test_scope_matrix_is_not_mutable_through_role_values():
    assert isinstance(ALL_SCOPES, frozenset)
    assert all(isinstance(scopes, frozenset) for scopes in ROLE_SCOPES.values())
