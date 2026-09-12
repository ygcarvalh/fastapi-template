"""gate settings behind a permission

Revision ID: b7d3e91af204
Revises: c4a17d59f8b2
Create Date: 2026-09-12 13:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3e91af204"
down_revision: Union[str, Sequence[str], None] = "c4a17d59f8b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HOLDERS = ("user", "superadmin")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO permissions (resource, action) VALUES ('settings', 'read') "
            "ON CONFLICT (resource, action) DO NOTHING"
        )
    )
    for role in HOLDERS:
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id, scope) "
                "SELECT r.id, p.id, 'all' FROM roles r, permissions p "
                "WHERE r.name = :role AND p.resource = 'settings' AND p.action = 'read' "
                "ON CONFLICT DO NOTHING"
            ).bindparams(role=role)
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE resource = 'settings' AND action = 'read')"
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE resource = 'settings' AND action = 'read'")
    )
