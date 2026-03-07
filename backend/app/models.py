from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AdminUser(Base, TimestampMixin):
    __tablename__ = 'admin_users'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Account(Base, TimestampMixin):
    __tablename__ = 'accounts'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_dynamic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_required_working_proxies: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Proxy(Base, TimestampMixin):
    __tablename__ = 'proxies'
    __table_args__ = (
        UniqueConstraint('host', 'port', 'auth_username', 'auth_password', name='uq_proxies_identity'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    host: Mapped[str] = mapped_column(INET, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    auth_username: Mapped[str | None] = mapped_column(Text)
    auth_password: Mapped[str | None] = mapped_column(Text)
    has_auth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(Text, default='new', nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    country_source: Mapped[str | None] = mapped_column(Text)
    country_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_threshold_ms: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_speedtest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_geo_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    aggregate: Mapped['ProxyAggregate | None'] = relationship(back_populates='proxy', uselist=False, cascade='all, delete-orphan')


class ProxyCheck(Base):
    __tablename__ = 'proxy_checks'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proxy_id: Mapped[int] = mapped_column(ForeignKey('proxies.id', ondelete='CASCADE'), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    check_no_in_window: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tcp_connect_ok: Mapped[bool | None] = mapped_column(Boolean)
    socks_handshake_ok: Mapped[bool | None] = mapped_column(Boolean)
    auth_ok: Mapped[bool | None] = mapped_column(Boolean)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProxySpeedtest(Base):
    __tablename__ = 'proxy_speedtests'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proxy_id: Mapped[int] = mapped_column(ForeignKey('proxies.id', ondelete='CASCADE'), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    partial_success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ping_ms: Mapped[float | None] = mapped_column(Numeric(10,2))
    jitter_ms: Mapped[float | None] = mapped_column(Numeric(10,2))
    download_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    upload_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    download_ok: Mapped[bool | None] = mapped_column(Boolean)
    upload_ok: Mapped[bool | None] = mapped_column(Boolean)
    ping_ok: Mapped[bool | None] = mapped_column(Boolean)
    raw_output: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ProxyGeoAttempt(Base):
    __tablename__ = 'proxy_geo_attempts'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proxy_id: Mapped[int] = mapped_column(ForeignKey('proxies.id', ondelete='CASCADE'), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detected_country_code: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProxyAggregate(Base):
    __tablename__ = 'proxy_aggregates'
    proxy_id: Mapped[int] = mapped_column(ForeignKey('proxies.id', ondelete='CASCADE'), primary_key=True)
    avg_latency_all_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_latency_day_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_latency_hour_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    min_latency_day_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    max_latency_day_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    success_rate_all: Mapped[float | None] = mapped_column(Numeric(8,5))
    success_rate_day: Mapped[float | None] = mapped_column(Numeric(8,5))
    success_rate_hour: Mapped[float | None] = mapped_column(Numeric(8,5))
    avg_download_all_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_upload_all_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_download_day_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_upload_day_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_ping_day_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_jitter_day_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    total_checks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_speedtests: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_success_checks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_failed_checks: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    flap_count_day: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flap_count_all: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stability_score: Mapped[float | None] = mapped_column(Numeric(12,5))
    composite_score: Mapped[float | None] = mapped_column(Numeric(12,5))
    quarantine_score: Mapped[float | None] = mapped_column(Numeric(12,5))
    real_traffic_avg_speed_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    current_active_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_active_connections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_sessions: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_connections: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_score_recalc_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    proxy: Mapped['Proxy'] = relationship(back_populates='aggregate')


class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'), nullable=False)
    client_ip: Mapped[str] = mapped_column(INET, nullable=False)
    client_login: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_proxy_id: Mapped[int | None] = mapped_column(ForeignKey('proxies.id'))
    sticky_proxy_id: Mapped[int | None] = mapped_column(ForeignKey('proxies.id'))
    strategy_variant: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default='active', nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    connections_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_connections_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_speed_in_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_speed_out_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_speed_total_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    kill_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SessionConnection(Base):
    __tablename__ = 'session_connections'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    proxy_id: Mapped[int | None] = mapped_column(ForeignKey('proxies.id'))
    target_host: Mapped[str] = mapped_column(Text, nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(Text, default='open', nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_speed_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    close_reason: Mapped[str | None] = mapped_column(Text)


class RoutingEvent(Base):
    __tablename__ = 'routing_events'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'))
    old_proxy_id: Mapped[int | None] = mapped_column(ForeignKey('proxies.id'))
    new_proxy_id: Mapped[int | None] = mapped_column(ForeignKey('proxies.id'))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    strategy_variant: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TrafficRollup(Base):
    __tablename__ = 'traffic_rollups'
    __table_args__ = (UniqueConstraint('scope_type', 'scope_id', 'bucket_type', 'bucket_start', name='uq_rollup'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    bucket_type: Mapped[str] = mapped_column(Text, nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    connections_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_speed_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))


class AccountAggregate(Base):
    __tablename__ = 'account_aggregates'
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id', ondelete='CASCADE'), primary_key=True)
    active_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_sessions: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_connections: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    avg_speed_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CountryAggregate(Base):
    __tablename__ = 'country_aggregates'
    country_code: Mapped[str] = mapped_column(Text, primary_key=True)
    total_proxies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    working_proxies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    online_proxies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    degraded_proxies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quarantined_proxies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_latency_day_ms: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_download_day_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    avg_upload_day_mbps: Mapped[float | None] = mapped_column(Numeric(12,3))
    active_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SystemSetting(Base):
    __tablename__ = 'system_settings'
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SchedulerState(Base):
    __tablename__ = 'scheduler_state'
    worker_name: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_cursor: Mapped[str | None] = mapped_column(Text)
    pause_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
