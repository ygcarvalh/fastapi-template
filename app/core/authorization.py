from app.models.role import Scope
from app.models.user import User, UserRole

ITEMS = "items"
REQUEST_LOG = "request_log"
USERS = "users"
ROLES = "roles"
FEATURE_FLAGS = "feature_flags"
SETTINGS = "settings"
AUDIT_LOG = "audit_log"

READ = "read"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
IMPERSONATE = "impersonate"


BASE_ROLES: dict[str, list[tuple[str, str, Scope]]] = {
    "user": [
        (ITEMS, READ, Scope.OWN),
        (ITEMS, CREATE, Scope.OWN),
        (ITEMS, UPDATE, Scope.OWN),
        (ITEMS, DELETE, Scope.OWN),
        (REQUEST_LOG, READ, Scope.OWN),
        (FEATURE_FLAGS, READ, Scope.ALL),
        (SETTINGS, READ, Scope.ALL),
    ],
    "superadmin": [
        (ITEMS, READ, Scope.OWN),
        (ITEMS, CREATE, Scope.OWN),
        (ITEMS, UPDATE, Scope.OWN),
        (ITEMS, DELETE, Scope.OWN),
        (REQUEST_LOG, READ, Scope.ALL),
        (USERS, READ, Scope.ALL),
        (USERS, UPDATE, Scope.ALL),
        (USERS, DELETE, Scope.ALL),
        (USERS, IMPERSONATE, Scope.ALL),
        (ROLES, READ, Scope.ALL),
        (ROLES, CREATE, Scope.ALL),
        (ROLES, UPDATE, Scope.ALL),
        (ROLES, DELETE, Scope.ALL),
        (FEATURE_FLAGS, READ, Scope.ALL),
        (FEATURE_FLAGS, UPDATE, Scope.ALL),
        (SETTINGS, READ, Scope.ALL),
        (AUDIT_LOG, READ, Scope.ALL),
    ],
}


# Acting as somebody else must never be a way to widen what they may do, so
# the reach that impersonation could hand over is closed for its duration.
BLOCKED_WHILE_IMPERSONATING: frozenset[tuple[str, str]] = frozenset(
    {
        (ROLES, CREATE),
        (ROLES, UPDATE),
        (ROLES, DELETE),
        (USERS, UPDATE),
        (USERS, DELETE),
        (USERS, IMPERSONATE),
        (FEATURE_FLAGS, UPDATE),
    }
)


def is_superuser(user: User) -> bool:
    return any(role.name == UserRole.ADMIN for role in user.roles)


def _widest(user: User) -> dict[tuple[str, str], Scope]:
    widest: dict[tuple[str, str], Scope] = {}
    for role in user.roles:
        for grant in role.grants:
            key = (grant.permission.resource, grant.permission.action)
            if widest.get(key) != Scope.ALL:
                widest[key] = grant.scope
    return widest


def scope_for(user: User, resource: str, action: str) -> Scope | None:
    if is_superuser(user):
        return Scope.ALL
    return _widest(user).get((resource, action))


# Reaching an account that outranks you is the same escalation whether you
# borrow it or close it, so both answer to one rule.
def outranks(actor: User, target: User) -> bool:
    return is_superuser(actor) or not is_superuser(target)


def may_impersonate(actor: User, target: User) -> bool:
    if scope_for(actor, USERS, IMPERSONATE) is None:
        return False
    return outranks(actor, target)


def granted(user: User) -> list[tuple[str, str, Scope]]:
    return [
        (resource, action, scope)
        for (resource, action), scope in sorted(_widest(user).items())
    ]
