from fastapi import APIRouter

from app.api.deps import RequireAuth
from app.core.features import enabled_features
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.feature import FeatureList

private_router = APIRouter(
    prefix="/features",
    tags=["features"],
    dependencies=[RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)


@private_router.get("")
async def list_features() -> FeatureList:
    return FeatureList(flags=sorted(enabled_features()))
