from datetime import UTC, datetime, timedelta

from app.models.single_use_token import SingleUseToken


def issued_within(token: SingleUseToken, now: datetime, cooldown: timedelta) -> bool:
    issued = token.created_at
    if issued is None:
        return False
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    return now - issued < cooldown
