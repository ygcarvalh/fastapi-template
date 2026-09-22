from dataclasses import dataclass

from app.core.i18n.locale import DEFAULT_LOCALE, Locale


@dataclass(frozen=True)
class Template:
    subject: str
    body: str


VERIFY_EMAIL = "verify-email"
RESET_PASSWORD = "reset-password"  # noqa: S105

TEMPLATES: dict[str, dict[Locale, Template]] = {
    VERIFY_EMAIL: {
        Locale.EN_US: Template(
            subject="Confirm your email address",
            body=(
                "Hello {name},\n\n"
                "Confirm this address to finish setting up your account:\n"
                "{link}\n\n"
                "The link stops working on {expires_at}.\n"
                "If you did not create this account, ignore this message."
            ),
        ),
        Locale.PT_BR: Template(
            subject="Confirme seu endereço de email",
            body=(
                "Olá, {name}.\n\n"
                "Confirme este endereço para terminar de configurar sua conta:\n"
                "{link}\n\n"
                "O link para de funcionar em {expires_at}.\n"
                "Se você não criou esta conta, ignore esta mensagem."
            ),
        ),
    },
    RESET_PASSWORD: {
        Locale.EN_US: Template(
            subject="Reset your password",
            body=(
                "Hello {name},\n\n"
                "Someone asked to reset the password for this account:\n"
                "{link}\n\n"
                "The link stops working on {expires_at} and can be used once.\n"
                "If it was not you, nothing has changed and you can ignore this."
            ),
        ),
        Locale.PT_BR: Template(
            subject="Redefina sua senha",
            body=(
                "Olá, {name}.\n\n"
                "Alguém pediu a redefinição da senha desta conta:\n"
                "{link}\n\n"
                "O link para de funcionar em {expires_at} e vale uma vez só.\n"
                "Se não foi você, nada mudou e pode ignorar esta mensagem."
            ),
        ),
    },
}


def render(name: str, locale: Locale, slots: dict[str, str]) -> Template:
    by_locale = TEMPLATES[name]
    template = by_locale.get(locale, by_locale[DEFAULT_LOCALE])
    return Template(
        subject=template.subject.format(**slots), body=template.body.format(**slots)
    )
