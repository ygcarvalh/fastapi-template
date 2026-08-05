from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.repositories.user_repo import UserRepository
from app.schemas.auth import Token
from app.services.auth_service import AuthService

public_router = APIRouter(prefix="/auth", tags=["auth"])


@public_router.post("/login")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    service = AuthService(UserRepository(session))
    token = await service.authenticate(form_data.username, form_data.password)
    return Token(access_token=token)
