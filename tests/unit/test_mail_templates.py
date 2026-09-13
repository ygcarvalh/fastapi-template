import re

from app.core.i18n.locale import DEFAULT_LOCALE, Locale
from app.core.mail.templates import TEMPLATES, render

SLOTS = {"name": "Ada", "link": "https://example.com", "expires_at": "tomorrow"}


def _slot_names(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def test_every_template_ships_every_locale() -> None:
    for name, by_locale in TEMPLATES.items():
        assert set(by_locale) == set(Locale), name


def test_a_translation_names_the_same_slots_as_the_default() -> None:
    for name, by_locale in TEMPLATES.items():
        expected = _slot_names(by_locale[DEFAULT_LOCALE].body)
        for locale, template in by_locale.items():
            assert _slot_names(template.body) == expected, (name, locale)


def test_every_template_interpolates_the_link_and_the_deadline() -> None:
    for name, by_locale in TEMPLATES.items():
        for locale, template in by_locale.items():
            assert {"link", "expires_at"} <= _slot_names(template.body), (name, locale)


def test_rendering_fills_every_slot() -> None:
    for name in TEMPLATES:
        for locale in Locale:
            rendered = render(name, locale, SLOTS)
            assert _slot_names(rendered.body) == set()
            assert rendered.subject.strip()
