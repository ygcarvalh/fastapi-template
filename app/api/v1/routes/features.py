from app.api.deps import CurrentUser
from app.api.v1.routing import protected_router
from app.core.features import enabled_features, inherited_features
from app.schemas.feature import FeatureList

private_router = protected_router(prefix="/features", tags=["features"])


# Pure function composition, no repository access — a service here would add
# indirection with no benefit.
@private_router.get("")
async def list_features(current_user: CurrentUser) -> FeatureList:
    inherited = inherited_features(
        [role.features for role in current_user.roles], enabled_features()
    )
    return FeatureList(
        flags=sorted(enabled_features()),
        inherited=None if inherited is None else sorted(inherited),
    )
