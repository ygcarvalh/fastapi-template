import pytest
from pydantic import ValidationError

from app.schemas.user import PasswordChange, UserUpdate


def test_an_email_cannot_be_cleared() -> None:
    with pytest.raises(ValidationError, match="email cannot be null"):
        UserUpdate(email=None)


def test_a_name_can_be_cleared() -> None:
    assert UserUpdate(name=None).name is None


def test_a_name_is_trimmed() -> None:
    assert UserUpdate(name="  Ada  ").name == "Ada"


def test_a_blank_name_is_refused() -> None:
    with pytest.raises(ValidationError, match="name cannot be blank"):
        UserUpdate(name="   ")


def test_the_new_password_must_differ() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        PasswordChange(current_password="secret123", new_password="secret123")


def test_an_oversized_password_is_refused() -> None:
    with pytest.raises(ValidationError):
        PasswordChange(current_password="secret123", new_password="a" * 73)
