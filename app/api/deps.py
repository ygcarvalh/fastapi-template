from typing import Annotated

from fastapi import Depends, params
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, ForbiddenError, NotFoundError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User, UserRole
from app.repositories.item_repo import ItemRepository
from app.repositories.user_repo import UserRepository
from app.services.item_service import ItemService
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_user_service(session: SessionDep) -> UserService:
    return UserService(UserRepository(session))


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_item_service(session: SessionDep) -> ItemService:
    return ItemService(ItemRepository(session))


ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: UserServiceDep,
) -> User:
    subject = decode_access_token(token)
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise AuthError("Invalid authentication credentials") from exc
    try:
        return await service.get(user_id)
    except NotFoundError as exc:
        raise AuthError("Invalid authentication credentials") from exc


CurrentUser = Annotated[User, Depends(get_current_user)]

RequireAuth = Depends(get_current_user)


def require_role(*allowed: UserRole) -> params.Depends:
    async def guard(current_user: CurrentUser) -> None:
        if current_user.role not in allowed:
            raise ForbiddenError("Insufficient permissions")

    dependency: params.Depends = Depends(guard)
    return dependency
