from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, ItemServiceDep, RequireAuth
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.schemas.pagination import Page, PageParams

private_router = APIRouter(prefix="/items", tags=["items"], dependencies=[RequireAuth])


@private_router.get("")
async def list_items(
    current_user: CurrentUser,
    service: ItemServiceDep,
    page: Annotated[PageParams, Query()],
) -> Page[ItemRead]:
    items, total = await service.list_for_owner(
        current_user.id, page.limit, page.offset
    )
    return Page(
        items=[ItemRead.model_validate(item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@private_router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    data: ItemCreate, current_user: CurrentUser, service: ItemServiceDep
) -> ItemRead:
    item = await service.create(current_user.id, data)
    return ItemRead.model_validate(item)


@private_router.get("/{item_id}")
async def get_item(
    item_id: int, current_user: CurrentUser, service: ItemServiceDep
) -> ItemRead:
    item = await service.get_for_owner(item_id, current_user.id)
    return ItemRead.model_validate(item)


@private_router.patch("/{item_id}")
async def update_item(
    item_id: int,
    data: ItemUpdate,
    current_user: CurrentUser,
    service: ItemServiceDep,
) -> ItemRead:
    item = await service.update(item_id, current_user.id, data)
    return ItemRead.model_validate(item)


@private_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int, current_user: CurrentUser, service: ItemServiceDep
) -> None:
    await service.delete(item_id, current_user.id)
