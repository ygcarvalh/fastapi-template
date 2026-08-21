from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Theme = Literal["light", "dark", "system"]

# A locale tag rather than a fixed list: the frontend owns which languages it
# ships, and the API only has to store one that cannot be a log-forging string.
Locale = Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Za-z0-9]{2,8})?$", max_length=10)]


class PreferencesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    locale: str
    theme: Theme
    show_request_id: bool


class PreferencesUpdate(BaseModel):
    locale: Locale | None = None
    theme: Theme | None = None
    show_request_id: bool | None = None
