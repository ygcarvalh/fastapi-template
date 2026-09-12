from app.models.role import Scope
from app.models.user import User

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
    "admin": [
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


def scope_for(user: User, resource: str, action: str) -> Scope | None:
    for grant in user.role.grants:
        if grant.permission.resource == resource and grant.permission.action == action:
            return grant.scope
    return None


def granted(user: User) -> list[tuple[str, str, Scope]]:
    return [
        (grant.permission.resource, grant.permission.action, grant.scope)
        for grant in user.role.grants
    ]
