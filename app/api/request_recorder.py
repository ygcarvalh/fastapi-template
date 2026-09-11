from app.db.session import get_session_factory
from app.repositories.request_log_repo import RequestLogRepository
from app.schemas.request_log import RequestRecord
from app.services.request_log_service import RequestLogService


# Wiring, so it lives with the composition root rather than in core: the
# middleware knows only the RequestRecorder callable it is handed.
# Its own session: the request-scoped one has already committed or rolled back
# by the time the middleware writes.
async def store_request(record: RequestRecord) -> None:
    async with get_session_factory()() as session:
        service = RequestLogService(RequestLogRepository(session))
        await service.record(record)
        await session.commit()
