from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.repositories.user_repo import UserRepository
from app.schemas.auth import RefreshRequest, Token
from app.services.auth_service import AuthService, TokenPair

public_router = APIRouter(prefix="/auth", tags=["auth"])


def _as_token(pair: TokenPair) -> Token:
    return Token(access_token=pair.access_token, refresh_token=pair.refresh_token)


@public_router.post("/login")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    service = AuthService(UserRepository(session))
    pair = await service.authenticate(form_data.username, form_data.password)
    return _as_token(pair)


@public_router.post("/refresh")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def refresh(
    request: Request,
    data: RefreshRequest,
    session: SessionDep,
) -> Token:
    service = AuthService(UserRepository(session))
    pair = await service.refresh(data.refresh_token)
    return _as_token(pair)
