from enum import StrEnum

from fastapi import Depends, params

from app.core.config import get_settings
from app.core.exceptions import NotFoundError


class Feature(StrEnum):
    ITEMS = "items"
    REQUEST_LOG = "request-log"


def parse_features(raw: str) -> frozenset[str]:
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def enabled_features() -> frozenset[Feature]:
    named = parse_features(get_settings().feature_flags)
    return frozenset(feature for feature in Feature if feature.value in named)


def is_enabled(feature: Feature) -> bool:
    return feature in enabled_features()


def available_features() -> list[str]:
    return sorted(feature.value for feature in enabled_features())


# A disabled route answers 404 rather than 403, so a flag that is off does not
# announce that the feature exists.
def require_feature(feature: Feature) -> params.Depends:
    async def guard() -> None:
        if not is_enabled(feature):
            raise NotFoundError("Not Found")

    dependency: params.Depends = Depends(guard)
    return dependency
