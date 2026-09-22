from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import quote

from fastapi import File, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import AttachmentServiceDep, CurrentUser
from app.api.v1.routing import protected_router
from app.core.features import Feature
from app.models.attachment import Attachment
from app.schemas.attachment import AttachmentRead
from app.services.attachment_service import Upload

item_attachments_router = protected_router(
    prefix="/items", tags=["attachments"], feature=Feature.ITEMS
)
attachments_router = protected_router(
    prefix="/attachments", tags=["attachments"], feature=Feature.ITEMS
)

CHUNK_BYTES = 64 * 1024


async def _chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK_BYTES):
        yield chunk


def _disposition(attachment: Attachment) -> str:
    ascii_name = attachment.filename.encode("ascii", "replace").decode()
    quoted = ascii_name.replace("\\", "_").replace('"', "_")
    encoded = quote(attachment.filename, safe="")
    return f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{encoded}"


@item_attachments_router.post(
    "/{item_id}/attachments", status_code=status.HTTP_201_CREATED
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


@item_attachments_router.get("/{item_id}/attachments")
async def list_attachments(
    item_id: int, current_user: CurrentUser, service: AttachmentServiceDep
) -> list[AttachmentRead]:
    stored = await service.list_for_item(item_id, current_user.id)
    return [AttachmentRead.model_validate(entry) for entry in stored]


@attachments_router.get("/{attachment_id}/content")
async def download_attachment(
    attachment_id: int, current_user: CurrentUser, service: AttachmentServiceDep
) -> StreamingResponse:
    stored = await service.get_for_owner(attachment_id, current_user.id)
    return StreamingResponse(
        service.read(stored),
        media_type=stored.content_type,
        headers={"Content-Disposition": _disposition(stored)},
    )


@attachments_router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_attachment(
    attachment_id: int, current_user: CurrentUser, service: AttachmentServiceDep
) -> None:
    await service.remove(attachment_id, current_user.id)
