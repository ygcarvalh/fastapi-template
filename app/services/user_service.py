from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.core.authorization import outranks
from app.core.error_codes import ErrorCode
from app.core.exceptions import ConflictError, ForbiddenError
from app.core.security import hash_password, verify_password
from app.models.role import Role
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.protocols import (
    ItemRepositoryProtocol,
    RoleRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.services.support import or_not_found

EMAIL_TAKEN = "Email already registered"
UNIQUE_VIOLATION = "23505"


# Only a unique violation is a conflict. A foreign key or a not-null failure is
# a bug on our side and stays a 500.
def _as_conflict(error: IntegrityError) -> Exception:
    if getattr(error.orig, "sqlstate", None) == UNIQUE_VIOLATION:
        return ConflictError(EMAIL_TAKEN, code=ErrorCode.USER_EMAIL_TAKEN)
    return error


class UserService:
    def __init__(
        self,
        repo: UserRepositoryProtocol,
        items: ItemRepositoryProtocol,
        roles: RoleRepositoryProtocol,
    ) -> None:
        self._repo = repo
        self._items = items
        self._roles = roles

    async def _role(self, name: str) -> Role:
        return or_not_found(
            await self._roles.get_by_name(name),
            "Role not found",
            ErrorCode.ROLE_NOT_FOUND,
        )

    async def _role_by_id(self, role_id: int) -> Role:
        return or_not_found(
            await self._roles.get(role_id), "Role not found", ErrorCode.ROLE_NOT_FOUND
        )

    async def add_role_by_id(self, user_id: int, role_id: int) -> User:
        role = await self._role_by_id(role_id)
        return await self.add_role(user_id, role.name)

    async def remove_role_by_id(self, actor: User, user_id: int, role_id: int) -> User:
        role = await self._role_by_id(role_id)
        return await self.remove_role(actor, user_id, role.name)

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_by_email(data.email) is not None:
            raise ConflictError(EMAIL_TAKEN, code=ErrorCode.USER_EMAIL_TAKEN)
        first = not await self._repo.exists_any()
        user = User(
            email=data.email,
            name=data.name,
            hashed_password=await hash_password(data.password),
            roles=[await self._role(UserRole.ADMIN if first else UserRole.USER)],
        )
        try:
            return await self._repo.create(user)
        except IntegrityError as error:
            raise _as_conflict(error) from error

    async def get(self, user_id: int) -> User:
        return or_not_found(
            await self._repo.get(user_id), "User not found", ErrorCode.USER_NOT_FOUND
        )

    async def update(self, user: User, data: UserUpdate) -> User:
        fields = data.model_dump(exclude_unset=True)
        email = fields.get("email")
        if email is not None and email != user.email:
            if await self._repo.get_by_email(email) is not None:
                raise ConflictError(EMAIL_TAKEN, code=ErrorCode.USER_EMAIL_TAKEN)
            user.email = email
        if "name" in fields:
            user.name = fields["name"]
        try:
            return await self._repo.save(user)
        except IntegrityError as error:
            raise _as_conflict(error) from error

    async def add_role(self, user_id: int, role_name: str) -> User:
        user = await self.get(user_id)
        role = await self._role(role_name)
        if any(held.name == role.name for held in user.roles):
            return user
        user.roles.append(role)
        return await self._repo.save(user)

    async def remove_role(self, actor: User, user_id: int, role_name: str) -> User:
        if actor.id == user_id and role_name == UserRole.ADMIN:
            raise ForbiddenError(
                "You cannot drop your own superadmin role",
                code=ErrorCode.USER_SELF_ADMIN_ROLE,
            )
        user = await self.get(user_id)
        role = await self._role(role_name)
        if not any(held.name == role.name for held in user.roles):
            return user
        user.roles = [held for held in user.roles if held.name != role.name]
        return await self._repo.save(user)

    async def list_all(self, limit: int, offset: int) -> tuple[Sequence[User], int]:
        users = await self._repo.list_all(limit, offset)
        total = await self._repo.count_all()
        return users, total

    # What the account owns goes with it, so a deactivated address that
    # registers again starts empty.
    async def deactivate(self, user: User, password: str) -> None:
        if not await verify_password(password, user.hashed_password):
            raise ForbiddenError(
                "Password is incorrect", code=ErrorCode.USER_PASSWORD_INCORRECT
            )
        await self._close(user)

    async def remove(self, actor: User, user_id: int) -> None:
        target = await self.get(user_id)
        if target.id == actor.id:
            raise ForbiddenError(
                "Close your own account from your profile",
                code=ErrorCode.USER_CLOSE_OWN_ACCOUNT,
            )
        if not outranks(actor, target):
            raise ForbiddenError(
                "Insufficient permissions",
                code=ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
            )
        await self._close(target)

    async def _close(self, user: User) -> None:
        await self._items.soft_delete_for_owner(user.id)
        await self._repo.soft_delete(user)
