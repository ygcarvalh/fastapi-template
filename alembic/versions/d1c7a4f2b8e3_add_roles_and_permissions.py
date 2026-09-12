"""add roles and permissions

Revision ID: d1c7a4f2b8e3
Revises: 0a456e5b983c
Create Date: 2026-09-11 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1c7a4f2b8e3"
down_revision: Union[str, Sequence[str], None] = "0a456e5b983c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS = [
    ("items", "read"),
    ("items", "create"),
    ("items", "update"),
    ("items", "delete"),
    ("request_log", "read"),
    ("users", "read"),
    ("users", "update"),
    ("roles", "read"),
    ("roles", "create"),
    ("roles", "update"),
    ("roles", "delete"),
    ("feature_flags", "read"),
]

GRANTS = {
    "user": [
        ("items", "read", "own"),
        ("items", "create", "own"),
        ("items", "update", "own"),
        ("items", "delete", "own"),
        ("request_log", "read", "own"),
        ("feature_flags", "read", "all"),
    ],
    "admin": [
        ("items", "read", "own"),
        ("items", "create", "own"),
        ("items", "update", "own"),
        ("items", "delete", "own"),
        ("request_log", "read", "all"),
        ("users", "read", "all"),
        ("users", "update", "all"),
        ("roles", "read", "all"),
        ("roles", "create", "all"),
        ("roles", "update", "all"),
        ("roles", "delete", "all"),
        ("feature_flags", "read", "all"),
    ],
}


def upgrade() -> None:
    """Upgrade schema."""
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )
    permissions = op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("resource", "action", name=op.f("uq_permissions_resource")),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "role_id", "permission_id", name=op.f("pk_role_permissions")
        ),
    )

    op.bulk_insert(roles, [{"name": name} for name in GRANTS])
    op.bulk_insert(
        permissions,
        [{"resource": resource, "action": action} for resource, action in PERMISSIONS],
    )
    for role_name, grants in GRANTS.items():
        for resource, action, scope in grants:
            op.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id, scope) "
                    "SELECT r.id, p.id, :scope FROM roles r, permissions p "
                    "WHERE r.name = :role AND p.resource = :resource "
                    "AND p.action = :action"
                ).bindparams(
                    scope=scope, role=role_name, resource=resource, action=action
                )
            )

    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text("UPDATE users SET role_id = (SELECT id FROM roles WHERE name = role)")
    )
    op.alter_column("users", "role_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_users_role_id_roles"), "users", "roles", ["role_id"], ["id"]
    )
    op.drop_column("users", "role")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=20), server_default="user", nullable=False),
    )
    op.execute(
        sa.text("UPDATE users SET role = (SELECT name FROM roles WHERE id = role_id)")
    )
    op.drop_constraint(op.f("fk_users_role_id_roles"), "users", type_="foreignkey")
    op.drop_column("users", "role_id")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
