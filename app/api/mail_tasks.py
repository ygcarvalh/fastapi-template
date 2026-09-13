from datetime import timedelta

import structlog

from app.api import deps
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.repositories.preferences_repo import PreferencesRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.single_use_token_repo import SingleUseTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.account_mailer import AccountMailer
from app.services.password_reset_service import PasswordResetService

logger = structlog.stdlib.get_logger("app.mail")


async def send_password_reset(email: str) -> None:
    settings = get_settings()
    try:
        async with get_session_factory()() as session:
            service = PasswordResetService(
                UserRepository(session),
                SingleUseTokenRepository(session),
                RefreshTokenRepository(session),
                AccountMailer(
                    deps.get_mail_sender(),
                    PreferencesRepository(session),
                    base_url=settings.app_base_url,
                ),
                lifetime=timedelta(minutes=settings.password_reset_expire_minutes),
                resend_cooldown=timedelta(
                    seconds=settings.mail_resend_cooldown_seconds
                ),
            )
            await service.request(email)
            await session.commit()
    except Exception:
        logger.warning("password_reset_mail_failed", exc_info=True)
