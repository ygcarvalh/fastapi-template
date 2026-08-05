from fastapi import APIRouter, status

from app.api.deps import CurrentUser, RequireAuth, UserServiceDep
from app.schemas.user import UserCreate, UserRead

public_router = APIRouter(prefix="/users", tags=["users"])
private_router = APIRouter(prefix="/users", tags=["users"], dependencies=[RequireAuth])


@public_router.post("", status_code=status.HTTP_201_CREATED)
async def register_user(data: UserCreate, service: UserServiceDep) -> UserRead:
    user = await service.register(data)
    return UserRead.model_validate(user)


@private_router.get("/me")
async def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
