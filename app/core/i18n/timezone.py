from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

DEFAULT_TIMEZONE = "UTC"


@lru_cache(maxsize=1)
def known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_known(name: str) -> bool:
    return name in known_timezones()


def resolve(stored: str | None) -> ZoneInfo:
    if stored is not None and is_known(stored):
        return ZoneInfo(stored)
    return ZoneInfo(DEFAULT_TIMEZONE)
