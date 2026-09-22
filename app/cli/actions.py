from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.core.storage.local import LocalStorage
from app.db.demo import seed_demo
from app.db.seed import seed_roles
from app.db.session import get_session_factory
from app.jobs.maintenance import (
    expire_tokens,
    prune_audit_log,
    prune_idempotency_keys,
    prune_request_log,
)
from app.models.role import Role
from app.models.user import User, UserRole
from app.repositories.user_repo import UserRepository
from app.schemas.user import normalize_email
from app.services.protocols import UserRepositoryProtocol


async def _load(users: UserRepositoryProtocol, email: str) -> User:
    user = await users.get_by_email(normalize_email(email))
    if user is None:
        raise NotFoundError(f"no account is registered as {email}")
    return user


async def _role(session: AsyncSession, name: str) -> Role:
    found = (
        await session.execute(select(Role).where(Role.name == name))
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError(f"no role is named {name}")
    return found


async def create_superuser(email: str, password: str) -> str:
    async with get_session_factory()() as session:
        users = UserRepository(session)
        if await users.get_by_email(normalize_email(email)) is not None:
            raise ConflictError(f"{email} is already registered")
        user = User(
            email=normalize_email(email),
            hashed_password=await hash_password(password),
            email_verified_at=datetime.now(UTC),
            roles=[await _role(session, UserRole.ADMIN)],
        )
        await users.create(user)
        await session.commit()
        return f"created {user.email} as {UserRole.ADMIN}"


async def grant_role(email: str, role_name: str) -> str:
    async with get_session_factory()() as session:
        users = UserRepository(session)
        user = await _load(users, email)
        role = await _role(session, role_name)
        if any(held.name == role.name for held in user.roles):
            return f"{user.email} already holds {role.name}"
        user.roles.append(role)
        await users.save(user)
        await session.commit()
        return f"{user.email} now holds {role.name}"


async def verify_email(email: str) -> str:
    async with get_session_factory()() as session:
        users = UserRepository(session)
        user = await _load(users, email)
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)
        await users.save(user)
        await session.commit()
        return f"{user.email} is confirmed"


async def seed() -> str:
    async with get_session_factory()() as session:
        if (await session.execute(select(Role))).scalars().first() is not None:
            return "roles are already seeded"
        await seed_roles(session)
        await session.commit()
        return "seeded the base roles"


async def demo_seed(if_enabled: bool = False) -> str:
    settings = get_settings()
    if if_enabled and not settings.demo_data_enabled:
        return "demo data is turned off"

    async with get_session_factory()() as session:
        if (await session.execute(select(User))).scalars().first() is not None:
            return "the database already has accounts; demo data was not written"

        if (await session.execute(select(Role))).scalars().first() is None:
            await seed_roles(session)

        counts = await seed_demo(session, LocalStorage(settings.storage_root))
        await session.commit()
        return (
            f"seeded {counts.users} demo users, {counts.items} items, "
            f"{counts.attachments} attachments"
        )


async def prune() -> str:
    settings = get_settings()
    audit = await prune_audit_log(timedelta(days=settings.audit_log_retention_days))
    requests = await prune_request_log(
        timedelta(days=settings.request_log_retention_days)
    )
    keys = await prune_idempotency_keys(
        timedelta(hours=settings.idempotency_retention_hours)
    )
    tokens = await expire_tokens()
    return (
        f"removed {audit} audit rows, {requests} request rows, "
        f"{keys} idempotency keys and {tokens} expired tokens"
    )
