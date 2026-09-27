"""initial schema

Accounts, sessions, ratings, mastery, parties, queue, servers, matches, allocations,
join tickets, results and per-player history.

Generated with ``alembic revision --autogenerate`` against an empty PostgreSQL 16 database
from ``wildrush_svc.models`` and reviewed by hand. ``tests/test_migrations.py`` runs
``alembic check`` so model/migration drift fails the test suite.

Revision ID: 0001
Revises:
Create Date: 2026-09-27 14:12:36.541503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=16), nullable=False),
    sa.Column('username_lower', sa.String(length=16), nullable=False),
    sa.Column('display_name', sa.String(length=20), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('selected_badge', sa.String(length=32), nullable=True),
    sa.CheckConstraint('username_lower = lower(username)', name=op.f('ck_accounts_username_lower')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_accounts')),
    sa.UniqueConstraint('username_lower', name=op.f('uq_accounts_username_lower'))
    )
    op.create_table('servers',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('region', sa.String(length=20), nullable=False),
    sa.Column('secret', sa.String(length=128), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('host', sa.String(length=255), nullable=True),
    sa.Column('port_min', sa.Integer(), nullable=True),
    sa.Column('port_max', sa.Integer(), nullable=True),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('build_id', sa.String(length=64), nullable=True),
    sa.Column('protocol', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_poll_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('active_matches', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('offline', 'online', 'draining')", name=op.f('ck_servers_status')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_servers'))
    )
    op.create_table('account_badges',
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('badge', sa.String(length=32), nullable=False),
    sa.Column('unlocked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('match_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_account_badges_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id', 'badge', name=op.f('pk_account_badges'))
    )
    op.create_table('fighter_mastery',
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('fighter', sa.String(length=8), nullable=False),
    sa.Column('xp', sa.Integer(), nullable=False),
    sa.Column('selected_palette', sa.String(length=16), nullable=False),
    sa.CheckConstraint("fighter IN ('nyx', 'bruno', 'vex', 'hops', 'scrap')", name=op.f('ck_fighter_mastery_fighter')),
    sa.CheckConstraint("selected_palette IN ('default', 'dusk', 'ember', 'frost')", name=op.f('ck_fighter_mastery_palette')),
    sa.CheckConstraint('xp >= 0', name=op.f('ck_fighter_mastery_xp_nonneg')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_fighter_mastery_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id', 'fighter', name=op.f('pk_fighter_mastery'))
    )
    op.create_table('matches',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('state', sa.String(length=12), nullable=False),
    sa.Column('region', sa.String(length=20), nullable=False),
    sa.Column('server_id', sa.String(length=40), nullable=True),
    sa.Column('host', sa.String(length=255), nullable=True),
    sa.Column('port', sa.Integer(), nullable=True),
    sa.Column('join_code', sa.String(length=8), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('expected_players', sa.Integer(), nullable=False),
    sa.Column('bot_slots', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.String(length=200), nullable=True),
    sa.CheckConstraint("mode IN ('casual', 'ranked', 'private')", name=op.f('ck_matches_mode')),
    sa.CheckConstraint("state IN ('allocating', 'ready', 'running', 'finished', 'cancelled')", name=op.f('ck_matches_state')),
    sa.ForeignKeyConstraint(['created_by'], ['accounts.id'], name=op.f('fk_matches_created_by_accounts')),
    sa.ForeignKeyConstraint(['server_id'], ['servers.id'], name=op.f('fk_matches_server_id_servers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_matches')),
    sa.UniqueConstraint('join_code', name=op.f('uq_matches_join_code'))
    )
    op.create_index('ix_matches_state', 'matches', ['state'], unique=False)
    op.create_table('parties',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('leader_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['leader_id'], ['accounts.id'], name=op.f('fk_parties_leader_id_accounts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parties'))
    )
    op.create_table('ratings',
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('rating', sa.Double(), nullable=False),
    sa.Column('deviation', sa.Double(), nullable=False),
    sa.Column('volatility', sa.Double(), nullable=False),
    sa.Column('games', sa.Integer(), nullable=False),
    sa.Column('wins', sa.Integer(), nullable=False),
    sa.Column('losses', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_ratings_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('account_id', name=op.f('pk_ratings'))
    )
    op.create_table('sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_sessions_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    op.create_index(op.f('ix_sessions_account_id'), 'sessions', ['account_id'], unique=False)
    op.create_table('allocations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('match_id', sa.UUID(), nullable=False),
    sa.Column('server_id', sa.String(length=40), nullable=False),
    sa.Column('state', sa.String(length=10), nullable=False),
    sa.Column('port', sa.Integer(), nullable=True),
    sa.Column('pid', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exit_code', sa.Integer(), nullable=True),
    sa.Column('end_reason', sa.String(length=200), nullable=True),
    sa.CheckConstraint("state IN ('pending', 'assigned', 'started', 'ended', 'cancelled')", name=op.f('ck_allocations_state')),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], name=op.f('fk_allocations_match_id_matches'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['server_id'], ['servers.id'], name=op.f('fk_allocations_server_id_servers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_allocations')),
    sa.UniqueConstraint('match_id', name=op.f('uq_allocations_match_id'))
    )
    op.create_index('ix_allocations_server_state', 'allocations', ['server_id', 'state'], unique=False)
    op.create_index('uq_allocations_server_port_active', 'allocations', ['server_id', 'port'], unique=True, postgresql_where=sa.text("state IN ('assigned', 'started')"))
    op.create_table('join_tickets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('match_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('server_id', sa.String(length=40), nullable=False),
    sa.Column('team', sa.SmallInteger(), nullable=False),
    sa.Column('role', sa.String(length=8), nullable=False),
    sa.Column('token', sa.Text(), nullable=False),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("role IN ('player', 'observer')", name=op.f('ck_join_tickets_role')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_join_tickets_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], name=op.f('fk_join_tickets_match_id_matches'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['server_id'], ['servers.id'], name=op.f('fk_join_tickets_server_id_servers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_join_tickets'))
    )
    op.create_index('ix_join_tickets_match_account', 'join_tickets', ['match_id', 'account_id'], unique=False)
    op.create_table('match_participants',
    sa.Column('match_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('team', sa.SmallInteger(), nullable=False),
    sa.Column('role', sa.String(length=8), nullable=False),
    sa.Column('lobby_admin', sa.Boolean(), nullable=False),
    sa.Column('party_id', sa.UUID(), nullable=True),
    sa.Column('roster_prefs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('player', 'observer')", name=op.f('ck_match_participants_role')),
    sa.CheckConstraint('team IN (-1, 0, 1)', name=op.f('ck_match_participants_team')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_match_participants_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], name=op.f('fk_match_participants_match_id_matches'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('match_id', 'account_id', name=op.f('pk_match_participants'))
    )
    op.create_index(op.f('ix_match_participants_account_id'), 'match_participants', ['account_id'], unique=False)
    op.create_table('match_player_results',
    sa.Column('match_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('team', sa.SmallInteger(), nullable=False),
    sa.Column('fighter', sa.String(length=8), nullable=False),
    sa.Column('won', sa.Boolean(), nullable=False),
    sa.Column('kos', sa.Integer(), nullable=False),
    sa.Column('knocked_out', sa.Integer(), nullable=False),
    sa.Column('damage_dealt', sa.Double(), nullable=False),
    sa.Column('control_seconds', sa.Double(), nullable=False),
    sa.Column('abandoned', sa.Boolean(), nullable=False),
    sa.Column('afk', sa.Boolean(), nullable=False),
    sa.Column('xp_gained', sa.Integer(), nullable=False),
    sa.Column('rating_before', sa.Double(), nullable=True),
    sa.Column('rating_after', sa.Double(), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_match_player_results_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], name=op.f('fk_match_player_results_match_id_matches'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('match_id', 'account_id', name=op.f('pk_match_player_results'))
    )
    op.create_index('ix_match_player_results_account_ended', 'match_player_results', ['account_id', 'ended_at'], unique=False)
    op.create_table('match_results',
    sa.Column('match_id', sa.UUID(), nullable=False),
    sa.Column('server_id', sa.String(length=40), nullable=False),
    sa.Column('body', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('body_sha256', sa.String(length=64), nullable=False),
    sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], name=op.f('fk_match_results_match_id_matches'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('match_id', name=op.f('pk_match_results'))
    )
    op.create_table('party_invites',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('party_id', sa.UUID(), nullable=False),
    sa.Column('from_account_id', sa.UUID(), nullable=False),
    sa.Column('to_account_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'expired', 'cancelled')", name=op.f('ck_party_invites_status')),
    sa.ForeignKeyConstraint(['from_account_id'], ['accounts.id'], name=op.f('fk_party_invites_from_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_party_invites_party_id_parties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_account_id'], ['accounts.id'], name=op.f('fk_party_invites_to_account_id_accounts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_party_invites'))
    )
    op.create_index('ix_party_invites_to_account_status', 'party_invites', ['to_account_id', 'status'], unique=False)
    op.create_index('uq_party_invites_pending', 'party_invites', ['party_id', 'to_account_id'], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_table('party_members',
    sa.Column('party_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_party_members_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_party_members_party_id_parties'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('party_id', 'account_id', name=op.f('pk_party_members')),
    sa.UniqueConstraint('account_id', name=op.f('uq_party_members_account_id'))
    )
    op.create_table('queue_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('leader_id', sa.UUID(), nullable=False),
    sa.Column('party_id', sa.UUID(), nullable=True),
    sa.Column('region', sa.String(length=20), nullable=False),
    sa.Column('latency_ms', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('allow_bots', sa.Boolean(), nullable=False),
    sa.Column('roster_prefs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("mode IN ('casual', 'ranked')", name=op.f('ck_queue_entries_mode')),
    sa.ForeignKeyConstraint(['leader_id'], ['accounts.id'], name=op.f('fk_queue_entries_leader_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_queue_entries_party_id_parties'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_queue_entries'))
    )
    op.create_index('ix_queue_entries_mode_queued_at', 'queue_entries', ['mode', 'queued_at'], unique=False)
    op.create_table('queue_members',
    sa.Column('entry_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_queue_members_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['entry_id'], ['queue_entries.id'], name=op.f('fk_queue_members_entry_id_queue_entries'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('entry_id', 'account_id', name=op.f('pk_queue_members')),
    sa.UniqueConstraint('account_id', name=op.f('uq_queue_members_account_id'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('queue_members')
    op.drop_index('ix_queue_entries_mode_queued_at', table_name='queue_entries')
    op.drop_table('queue_entries')
    op.drop_table('party_members')
    op.drop_index('uq_party_invites_pending', table_name='party_invites', postgresql_where=sa.text("status = 'pending'"))
    op.drop_index('ix_party_invites_to_account_status', table_name='party_invites')
    op.drop_table('party_invites')
    op.drop_table('match_results')
    op.drop_index('ix_match_player_results_account_ended', table_name='match_player_results')
    op.drop_table('match_player_results')
    op.drop_index(op.f('ix_match_participants_account_id'), table_name='match_participants')
    op.drop_table('match_participants')
    op.drop_index('ix_join_tickets_match_account', table_name='join_tickets')
    op.drop_table('join_tickets')
    op.drop_index('uq_allocations_server_port_active', table_name='allocations', postgresql_where=sa.text("state IN ('assigned', 'started')"))
    op.drop_index('ix_allocations_server_state', table_name='allocations')
    op.drop_table('allocations')
    op.drop_index(op.f('ix_sessions_account_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('ratings')
    op.drop_table('parties')
    op.drop_index('ix_matches_state', table_name='matches')
    op.drop_table('matches')
    op.drop_table('fighter_mastery')
    op.drop_table('account_badges')
    op.drop_table('servers')
    op.drop_table('accounts')
