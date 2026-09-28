"""history rows for ranked no-shows

Ranked players who never joined (no ticket redeemed) are rated as abandoned and get a
history row without a fighter, so ``match_player_results.fighter`` becomes nullable.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-27 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('match_player_results', 'fighter',
               existing_type=sa.String(length=8),
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE match_player_results SET fighter = '' WHERE fighter IS NULL")
    op.alter_column('match_player_results', 'fighter',
               existing_type=sa.String(length=8),
               nullable=False)
