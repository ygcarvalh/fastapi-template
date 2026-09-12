"""gate the audit log behind a permission

Revision ID: c81a4f7b2d55
Revises: 9683fb4021be
Create Date: 2026-09-12 14:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c81a4f7b2d55"
down_revision: Union[str, Sequence[str], None] = "9683fb4021be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO permissions (resource, action) "
            "VALUES ('audit_log', 'read') "
            "ON CONFLICT (resource, action) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id, scope) "
            "SELECT r.id, p.id, 'all' FROM roles r, permissions p "
            "WHERE r.name = 'superadmin' "
            "AND p.resource = 'audit_log' AND p.action = 'read' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions "
            "WHERE resource = 'audit_log' AND action = 'read')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions "
            "WHERE resource = 'audit_log' AND action = 'read'"
        )
    )
