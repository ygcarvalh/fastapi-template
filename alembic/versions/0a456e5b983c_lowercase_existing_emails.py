"""lowercase existing emails

Revision ID: 0a456e5b983c
Revises: 41ffc6580287
Create Date: 2026-09-11 10:37:31.794728

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0a456e5b983c'
down_revision: Union[str, Sequence[str], None] = '41ffc6580287'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")


def downgrade() -> None:
    pass
