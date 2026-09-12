"""let feature flags be delegated

Revision ID: f5c8021ea6b1
Revises: b7d3e91af204
Create Date: 2026-09-12 14:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5c8021ea6b1"
down_revision: Union[str, Sequence[str], None] = "b7d3e91af204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO permissions (resource, action) "
            "VALUES ('feature_flags', 'update') "
            "ON CONFLICT (resource, action) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id, scope) "
            "SELECT r.id, p.id, 'all' FROM roles r, permissions p "
            "WHERE r.name = 'superadmin' AND p.resource = 'feature_flags' "
            "AND p.action = 'update' ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE resource = 'feature_flags' "
            "AND action = 'update')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE resource = 'feature_flags' "
            "AND action = 'update'"
        )
    )
