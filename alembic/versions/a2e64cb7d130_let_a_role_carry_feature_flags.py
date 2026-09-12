"""let a role carry feature flags

Revision ID: a2e64cb7d130
Revises: f5c8021ea6b1
Create Date: 2026-09-12 14:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2e64cb7d130"
down_revision: Union[str, Sequence[str], None] = "f5c8021ea6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("roles", sa.Column("features", sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("roles", "features")
