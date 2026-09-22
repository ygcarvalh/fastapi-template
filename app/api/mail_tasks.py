import structlog

from app.api import deps
from app.db.session import get_session_factory

logger = structlog.stdlib.get_logger("app.mail")


async def send_password_reset(email: str) -> None:
    try:
        async with get_session_factory()() as session:
            service = deps.build_password_reset_service(session)
            await service.request(email)
            await session.commit()
    except Exception:
        logger.warning("password_reset_mail_failed", exc_info=True)
