from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.context import audit_suppressed
from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.core.storage.backend import Storage
from app.models.attachment import Attachment
from app.models.item import Item
from app.models.role import Role
from app.models.user import User, UserRole
from app.models.user_preferences import UserPreferences

DEMO_PASSWORD = "Change!123"


@dataclass
class DemoItem:
    title: str
    description: str
    deleted: bool = False


@dataclass
class DemoAttachment:
    item_title: str
    filename: str
    content_type: str
    content: bytes


@dataclass
class DemoUser:
    email: str
    role: str
    verified: bool = True
    preferences: dict[str, str] | None = None
    items: list[DemoItem] = field(default_factory=list)
    attachments: list[DemoAttachment] = field(default_factory=list)


DEMO_USERS: list[DemoUser] = [
    DemoUser(email="admin@example.com", role=UserRole.ADMIN),
    DemoUser(
        email="alice@example.com",
        role=UserRole.USER,
        preferences={
            "locale": "pt-BR",
            "theme": "dark",
            "timezone": "America/Sao_Paulo",
        },
        items=[
            DemoItem(
                "Draft the onboarding guide",
                "Cover the demo flag and the login flow",
            ),
            DemoItem(
                "Review pull request #42",
                "Check the migration drift test still passes",
            ),
            DemoItem(
                "Retired planning doc",
                "No longer needed now that the roadmap moved",
                deleted=True,
            ),
        ],
        attachments=[
            DemoAttachment(
                item_title="Draft the onboarding guide",
                filename="notes.txt",
                content_type="text/plain",
                content=b"Remember to mention the DEMO_DATA_ENABLED flag.\n",
            ),
        ],
    ),
    DemoUser(
        email="bob@example.com",
        role=UserRole.USER,
        items=[
            DemoItem("Set up the staging environment", "Point it at the demo dataset"),
            DemoItem("Write the release notes", "Summarize the demo-seed command"),
            DemoItem(
                "Fix the flaky rate-limit test", "It fails under load, not in isolation"
            ),
        ],
    ),
    DemoUser(email="carol@example.com", role=UserRole.USER, verified=False),
]


class DemoCounts(NamedTuple):
    users: int
    items: int
    attachments: int


async def _one_chunk(content: bytes) -> AsyncIterator[bytes]:
    yield content


async def _role(session: AsyncSession, name: str) -> Role:
    found = (
        await session.execute(select(Role).where(Role.name == name))
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError(f"no role is named {name}")
    return found


async def seed_demo(session: AsyncSession, storage: Storage) -> DemoCounts:
    with audit_suppressed():
        hashed_password = hash_password(DEMO_PASSWORD)
        users = 0
        items = 0
        attachments = 0

        for demo_user in DEMO_USERS:
            role = await _role(session, demo_user.role)
            user = User(
                email=demo_user.email,
                hashed_password=hashed_password,
                email_verified_at=datetime.now(UTC) if demo_user.verified else None,
                roles=[role],
            )
            session.add(user)
            await session.flush()
            users += 1

            if demo_user.preferences is not None:
                session.add(UserPreferences(user_id=user.id, **demo_user.preferences))

            items_by_title: dict[str, Item] = {}
            for demo_item in demo_user.items:
                item = Item(
                    title=demo_item.title,
                    description=demo_item.description,
                    owner_id=user.id,
                )
                session.add(item)
                await session.flush()
                if demo_item.deleted:
                    item.mark_deleted()
                items_by_title[demo_item.title] = item
                items += 1

            for demo_attachment in demo_user.attachments:
                item = items_by_title[demo_attachment.item_title]
                key = f"demo/{item.id}/{demo_attachment.filename}"
                stored = await storage.save(key, _one_chunk(demo_attachment.content))
                session.add(
                    Attachment(
                        key=stored.key,
                        filename=demo_attachment.filename,
                        content_type=demo_attachment.content_type,
                        size_bytes=stored.size_bytes,
                        item_id=item.id,
                    )
                )
                attachments += 1

        await session.flush()
        return DemoCounts(users=users, items=items, attachments=attachments)
