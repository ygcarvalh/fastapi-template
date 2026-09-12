"""rename the admin role

Revision ID: e2f8b1c4d906
Revises: d1c7a4f2b8e3
Create Date: 2026-09-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f8b1c4d906"
down_revision: Union[str, Sequence[str], None] = "d1c7a4f2b8e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("UPDATE roles SET name = 'superadmin' WHERE name = 'admin'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("UPDATE roles SET name = 'admin' WHERE name = 'superadmin'"))
