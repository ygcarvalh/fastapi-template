from app.models.role import Scope
from app.models.user import User, UserRole

ITEMS = "items"
REQUEST_LOG = "request_log"
USERS = "users"
ROLES = "roles"
FEATURE_FLAGS = "feature_flags"

READ = "read"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"


BASE_ROLES: dict[str, list[tuple[str, str, Scope]]] = {
    "user": [
        (ITEMS, READ, Scope.OWN),
        (ITEMS, CREATE, Scope.OWN),
        (ITEMS, UPDATE, Scope.OWN),
        (ITEMS, DELETE, Scope.OWN),
        (REQUEST_LOG, READ, Scope.OWN),
        (FEATURE_FLAGS, READ, Scope.ALL),
    ],
    "superadmin": [
        (ITEMS, READ, Scope.OWN),
        (ITEMS, CREATE, Scope.OWN),
        (ITEMS, UPDATE, Scope.OWN),
        (ITEMS, DELETE, Scope.OWN),
        (REQUEST_LOG, READ, Scope.ALL),
        (USERS, READ, Scope.ALL),
        (USERS, UPDATE, Scope.ALL),
        (ROLES, READ, Scope.ALL),
        (ROLES, CREATE, Scope.ALL),
        (ROLES, UPDATE, Scope.ALL),
        (ROLES, DELETE, Scope.ALL),
        (FEATURE_FLAGS, READ, Scope.ALL),
    ],
}


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


def granted(user: User) -> list[tuple[str, str, Scope]]:
    return [
        (resource, action, scope)
        for (resource, action), scope in sorted(_widest(user).items())
    ]
