"""let an account hold several roles

Revision ID: c4a17d59f8b2
Revises: e2f8b1c4d906
Create Date: 2026-09-12 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4a17d59f8b2"
down_revision: Union[str, Sequence[str], None] = "e2f8b1c4d906"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_roles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_user_roles_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_roles")),
    )
    op.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_id) SELECT id, role_id FROM users"
        )
    )
    op.drop_constraint(op.f("fk_users_role_id_roles"), "users", type_="foreignkey")
    op.drop_column("users", "role_id")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE users SET role_id = ("
            "SELECT MIN(role_id) FROM user_roles WHERE user_id = users.id)"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'user') "
            "WHERE role_id IS NULL"
        )
    )
    op.alter_column("users", "role_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_users_role_id_roles"), "users", "roles", ["role_id"], ["id"]
    )
    op.drop_table("user_roles")
