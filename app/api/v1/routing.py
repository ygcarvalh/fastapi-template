from enum import Enum

from fastapi import APIRouter, params

from app.api.deps import RequireAuth
from app.core.features import Feature, require_feature
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES

__all__ = ["protected_router"]


def protected_router(
    *, prefix: str, tags: list[str | Enum], feature: Feature | None = None
) -> APIRouter:
    dependencies: list[params.Depends] = (
        [RequireAuth] if feature is None else [require_feature(feature), RequireAuth]
    )
    return APIRouter(
        prefix=prefix,
        tags=tags,
        dependencies=dependencies,
        responses=AUTHENTICATED_ERROR_RESPONSES,
    )
