"""initial schema"""

from pathlib import Path

from alembic import op

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_path = Path(__file__).resolve().parents[2] / 'app' / 'sql' / 'schema.sql'
    op.execute(schema_path.read_text())


def downgrade() -> None:
    for stmt in [
        'drop view if exists v_active_sessions',
        'drop view if exists v_country_account_candidates',
        'drop view if exists v_working_proxies',
        'drop table if exists audit_logs cascade',
        'drop table if exists scheduler_state cascade',
        'drop table if exists system_settings cascade',
        'drop table if exists country_aggregates cascade',
        'drop table if exists account_aggregates cascade',
        'drop table if exists traffic_rollups cascade',
        'drop table if exists routing_events cascade',
        'drop table if exists session_connections cascade',
        'drop table if exists sessions cascade',
        'drop table if exists proxy_health_windows cascade',
        'drop table if exists proxy_aggregates cascade',
        'drop table if exists proxy_geo_attempts cascade',
        'drop table if exists proxy_speedtests cascade',
        'drop table if exists proxy_checks cascade',
        'drop table if exists proxy_tags cascade',
        'drop table if exists proxies cascade',
        'drop table if exists accounts cascade',
        'drop table if exists admin_users cascade',
        'drop function if exists set_updated_at() cascade',
        'drop extension if exists pgcrypto',
    ]:
        op.execute(stmt)
