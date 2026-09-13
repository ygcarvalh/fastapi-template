from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import AttachmentServiceDep, CurrentUser, RequireAuth
from app.core.features import Feature, require_feature
from app.models.attachment import Attachment
from app.schemas.attachment import AttachmentRead
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.services.attachment_service import Upload

private_router = APIRouter(
    tags=["attachments"],
    dependencies=[require_feature(Feature.ITEMS), RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)

CHUNK_BYTES = 64 * 1024


async def _chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK_BYTES):
        yield chunk


def _disposition(attachment: Attachment) -> str:
    return f'attachment; filename="{attachment.filename}"'


@private_router.post(
    "/items/{item_id}/attachments", status_code=status.HTTP_201_CREATED
)
async def add_attachment(
    item_id: int,
    current_user: CurrentUser,
    service: AttachmentServiceDep,
    file: Annotated[UploadFile, File()],
) -> AttachmentRead:
    stored = await service.add(
        item_id,
        current_user.id,
        Upload(file.filename, file.content_type, _chunks(file)),
    )
    return AttachmentRead.model_validate(stored)


@private_router.get("/items/{item_id}/attachments")
async def list_attachments(
    item_id: int, current_user: CurrentUser, service: AttachmentServiceDep
) -> list[AttachmentRead]:
    stored = await service.list_for_item(item_id, current_user.id)
    return [AttachmentRead.model_validate(entry) for entry in stored]


@private_router.get("/attachments/{attachment_id}/content")
async def download_attachment(
    attachment_id: int, current_user: CurrentUser, service: AttachmentServiceDep
) -> StreamingResponse:
    stored = await service.get_for_owner(attachment_id, current_user.id)
    return StreamingResponse(
        service.read(stored),
        media_type=stored.content_type,
        headers={"Content-Disposition": _disposition(stored)},
    )


@private_router.delete(
    "/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_attachment(
    attachment_id: int, current_user: CurrentUser, service: AttachmentServiceDep
) -> None:
    await service.remove(attachment_id, current_user.id)
