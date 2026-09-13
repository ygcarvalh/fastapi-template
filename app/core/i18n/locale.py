from enum import StrEnum


class Locale(StrEnum):
    EN_US = "en-US"
    PT_BR = "pt-BR"


DEFAULT_LOCALE = Locale.EN_US

_BY_LANGUAGE = {locale.value.split("-")[0]: locale for locale in Locale}


def coerce(tag: str | None) -> Locale | None:
    if tag is None:
        return None
    cleaned = tag.strip().lower()
    if not cleaned:
        return None
    for locale in Locale:
        if locale.value.lower() == cleaned:
            return locale
    return _BY_LANGUAGE.get(cleaned.split("-")[0])


def ranked_tags(accept_language: str | None) -> list[str]:
    if not accept_language:
        return []
    weighted: list[tuple[float, str]] = []
    for entry in accept_language.split(","):
        tag, _, parameters = entry.strip().partition(";")
        quality = _quality(parameters)
        if tag.strip() and quality > 0:
            weighted.append((quality, tag.strip()))
    return [tag for _, tag in sorted(weighted, key=lambda pair: pair[0], reverse=True)]


def negotiate(accept_language: str | None) -> Locale | None:
    for tag in ranked_tags(accept_language):
        found = coerce(tag)
        if found is not None:
            return found
    return None


def resolve(stored: str | None, accept_language: str | None = None) -> Locale:
    return coerce(stored) or negotiate(accept_language) or DEFAULT_LOCALE


def _quality(parameters: str) -> float:
    cleaned = parameters.strip()
    if not cleaned.startswith("q="):
        return 1.0
    try:
        return float(cleaned[2:])
    except ValueError:
        return 0.0
