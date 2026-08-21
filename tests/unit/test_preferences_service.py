from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.schemas.preferences import PreferencesUpdate
from app.services.preferences_service import PreferencesService
from tests.unit.fakes import FakePreferencesRepository


def _user(user_id: int = 1) -> User:
    return User(id=user_id, email="user@example.com", hashed_password="x")


async def test_an_account_without_a_row_gets_the_defaults() -> None:
    service = PreferencesService(FakePreferencesRepository())

    preferences = await service.get(_user())

    assert (preferences.locale, preferences.theme, preferences.show_request_id) == (
        "en-US",
        "system",
        True,
    )


async def test_the_first_change_writes_a_row() -> None:
    repo = FakePreferencesRepository()
    service = PreferencesService(repo)

    saved = await service.update(_user(), PreferencesUpdate(locale="pt-BR"))

    assert saved.locale == "pt-BR"
    assert len(repo.created) == 1


async def test_a_later_change_updates_the_row() -> None:
    repo = FakePreferencesRepository(UserPreferences(user_id=1, locale="pt-BR"))
    service = PreferencesService(repo)

    saved = await service.update(_user(), PreferencesUpdate(theme="dark"))

    assert (saved.locale, saved.theme) == ("pt-BR", "dark")
    assert repo.created == []
    assert len(repo.saved) == 1


async def test_fields_left_out_are_untouched() -> None:
    repo = FakePreferencesRepository(
        UserPreferences(user_id=1, locale="pt-BR", theme="dark", show_request_id=False)
    )

    saved = await PreferencesService(repo).update(_user(), PreferencesUpdate())

    assert (saved.locale, saved.theme, saved.show_request_id) == (
        "pt-BR",
        "dark",
        False,
    )
