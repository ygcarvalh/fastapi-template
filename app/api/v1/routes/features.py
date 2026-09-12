from fastapi import APIRouter

from app.api.deps import CurrentUser, RequireAuth
from app.core.features import enabled_features, inherited_features
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.feature import FeatureList

private_router = APIRouter(
    prefix="/features",
    tags=["features"],
    dependencies=[RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)


@private_router.get("")
async def list_features(current_user: CurrentUser) -> FeatureList:
    inherited = inherited_features(
        [role.features for role in current_user.roles], enabled_features()
    )
    return FeatureList(
        flags=sorted(enabled_features()),
        inherited=None if inherited is None else sorted(inherited),
    )
