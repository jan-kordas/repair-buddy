"""seed default user

Revision ID: a81e3379bc7b
Revises: 1c89a8ee43cd
Create Date: 2026-06-04 21:58:43.466474

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a81e3379bc7b"
down_revision: str | Sequence[str] | None = "1c89a8ee43cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("INSERT INTO users (id) VALUES (1) ON CONFLICT DO NOTHING")
    op.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), 1, true)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM users WHERE id = 1")
