"""add audit logs

Revision ID: 9683fb4021be
Revises: a2e64cb7d130
Create Date: 2026-09-12 13:44:34.401333

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9683fb4021be"
down_revision: Union[str, Sequence[str], None] = "a2e64cb7d130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("impersonator_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("table_name", sa.String(length=63), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("row_pk", sa.String(length=128), nullable=True),
        sa.Column(
            "changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "truncated", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_actor_id_occurred_at",
        "audit_logs",
        ["actor_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_logs_occurred_at"), "audit_logs", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_audit_logs_request_id"), "audit_logs", ["request_id"], unique=False
    )
    op.create_index(
        "ix_audit_logs_table_name_row_pk",
        "audit_logs",
        ["table_name", "row_pk"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_audit_logs_table_name_row_pk", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_request_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_occurred_at"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id_occurred_at", table_name="audit_logs")
    op.drop_table("audit_logs")
