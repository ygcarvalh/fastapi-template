from enum import StrEnum


class AuditAction(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    SOFT_DELETE = "soft_delete"
    RESTORE = "restore"
    LINK = "link"
    UNLINK = "unlink"
    IMPERSONATE_START = "impersonate_start"
    IMPERSONATE_STOP = "impersonate_stop"


EXCLUDED_TABLES = frozenset(
    {"audit_logs", "request_logs", "refresh_tokens", "alembic_version"}
)

REDACTED_COLUMNS = frozenset(
    {"hashed_password", "token_hash", "password", "secret", "api_key"}
)

IGNORED_COLUMNS = frozenset({"created_at", "updated_at"})

REDACTED_PLACEHOLDER = "***"

MAX_VALUE_CHARS = 1000
MAX_DOCUMENT_BYTES = 64 * 1024


def is_audited(table_name: str) -> bool:
    return table_name not in EXCLUDED_TABLES


def is_redacted(column: str) -> bool:
    return column in REDACTED_COLUMNS


def is_ignored(column: str) -> bool:
    return column in IGNORED_COLUMNS
