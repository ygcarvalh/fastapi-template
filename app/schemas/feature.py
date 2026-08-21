from pydantic import BaseModel

from app.core.features import Feature


class FeatureList(BaseModel):
    flags: list[Feature]
