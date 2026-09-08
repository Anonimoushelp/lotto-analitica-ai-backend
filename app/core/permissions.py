from typing import Final, Literal

Role = Literal["admin", "analyst", "viewer", "service"]
Scope = Literal[
    "lotteries:read",
    "lotteries:write",
    "draws:read",
    "draws:write",
    "predictions:read",
    "predictions:generate",
    "analytics:read",
    "crypto:use",
    "tenant:manage",
    "memberships:manage",
]

ALL_SCOPES: Final[frozenset[Scope]] = frozenset(
    {
        "lotteries:read",
        "lotteries:write",
        "draws:read",
        "draws:write",
        "predictions:read",
        "predictions:generate",
        "analytics:read",
        "crypto:use",
        "tenant:manage",
        "memberships:manage",
    }
)

ROLE_SCOPES: Final[dict[Role, frozenset[Scope]]] = {
    "admin": ALL_SCOPES,
    "analyst": frozenset(
        {
            "lotteries:read",
            "draws:read",
            "predictions:read",
            "predictions:generate",
            "analytics:read",
            "crypto:use",
        }
    ),
    "viewer": frozenset(),
    "service": frozenset(),
}


def has_scope(role: Role, scope: Scope) -> bool:
    return scope in ROLE_SCOPES[role]
