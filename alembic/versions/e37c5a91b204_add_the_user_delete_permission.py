"""add the user delete permission

Revision ID: e37c5a91b204
Revises: d94b6e0f3a17
Create Date: 2026-09-12 15:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e37c5a91b204"
down_revision: Union[str, Sequence[str], None] = "d94b6e0f3a17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO permissions (resource, action) "
            "VALUES ('users', 'delete') "
            "ON CONFLICT (resource, action) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id, scope) "
            "SELECT r.id, p.id, 'all' FROM roles r, permissions p "
            "WHERE r.name = 'superadmin' "
            "AND p.resource = 'users' AND p.action = 'delete' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions "
            "WHERE resource = 'users' AND action = 'delete')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE resource = 'users' AND action = 'delete'"
        )
    )
