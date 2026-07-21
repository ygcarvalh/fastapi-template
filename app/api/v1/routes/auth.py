from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.repositories.user_repo import UserRepository
from app.schemas.auth import Token
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> Token:
    service = AuthService(UserRepository(session))
    token = await service.authenticate(form_data.username, form_data.password)
    return Token(access_token=token)
