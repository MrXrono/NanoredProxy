-- =========================================================
-- Project: NanoredProxy
-- DB: PostgreSQL
-- =========================================================

create extension if not exists pgcrypto;

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create table if not exists admin_users (
    id bigserial primary key,
    username text not null unique,
    password text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_login_at timestamptz
);

create table if not exists accounts (
    id bigserial primary key,
    username text not null unique,
    password text not null,
    account_type text not null check (account_type in ('all', 'country')),
    country_code text,
    is_enabled boolean not null default true,
    is_dynamic boolean not null default false,
    min_required_working_proxies integer not null default 2,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_reconciled_at timestamptz,
    constraint accounts_country_rule_chk check (
        (account_type = 'all' and country_code is null)
        or
        (account_type = 'country' and country_code is not null)
    )
);

create table if not exists proxies (
    id bigserial primary key,
    host inet not null,
    port integer not null check (port > 0 and port <= 65535),
    auth_username text,
    auth_password text,
    has_auth boolean not null default false,
    status text not null default 'new' check (status in ('new','checking','online','degraded','offline','quarantine','country_unknown','disabled')),
    country_code text,
    country_source text check (country_source in ('auto','manual','unknown')),
    country_manual_override boolean not null default false,
    latency_threshold_ms integer not null default 1500,
    is_enabled boolean not null default true,
    is_quarantined boolean not null default false,
    first_seen_at timestamptz not null default now(),
    last_checked_at timestamptz,
    last_success_at timestamptz,
    last_failure_at timestamptz,
    last_speedtest_at timestamptz,
    last_geo_attempt_at timestamptz,
    last_error_code text,
    last_error_message text,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_proxies_identity on proxies(host, port, coalesce(auth_username, ''), coalesce(auth_password, ''));
create index if not exists idx_proxies_status on proxies(status);
create index if not exists idx_proxies_country_code on proxies(country_code);
create index if not exists idx_proxies_enabled on proxies(is_enabled);
create index if not exists idx_proxies_quarantined on proxies(is_quarantined);

create table if not exists proxy_checks (
    id bigserial primary key,
    proxy_id bigint not null references proxies(id) on delete cascade,
    batch_id uuid,
    check_no_in_window smallint,
    success boolean not null,
    tcp_connect_ok boolean,
    socks_handshake_ok boolean,
    auth_ok boolean,
    latency_ms integer,
    error_code text,
    error_message text,
    checked_at timestamptz not null default now()
);

create table if not exists proxy_speedtests (
    id bigserial primary key,
    proxy_id bigint not null references proxies(id) on delete cascade,
    started_at timestamptz not null,
    finished_at timestamptz,
    success boolean not null default false,
    partial_success boolean not null default false,
    ping_ms numeric(10,2),
    jitter_ms numeric(10,2),
    download_mbps numeric(12,3),
    upload_mbps numeric(12,3),
    download_ok boolean,
    upload_ok boolean,
    ping_ok boolean,
    raw_output text,
    error_code text,
    error_message text
);

create table if not exists proxy_geo_attempts (
    id bigserial primary key,
    proxy_id bigint not null references proxies(id) on delete cascade,
    success boolean not null,
    detected_country_code text,
    source text not null check (source in ('auto', 'manual')),
    error_message text,
    attempted_at timestamptz not null default now()
);

create table if not exists proxy_aggregates (
    proxy_id bigint primary key references proxies(id) on delete cascade,
    avg_latency_all_ms numeric(12,3),
    avg_latency_day_ms numeric(12,3),
    avg_latency_hour_ms numeric(12,3),
    success_rate_all numeric(8,5),
    success_rate_day numeric(8,5),
    success_rate_hour numeric(8,5),
    avg_download_day_mbps numeric(12,3),
    avg_upload_day_mbps numeric(12,3),
    stability_score numeric(12,5),
    composite_score numeric(12,5),
    quarantine_score numeric(12,5),
    current_active_sessions integer not null default 0,
    current_active_connections integer not null default 0,
    total_sessions bigint not null default 0,
    total_connections bigint not null default 0,
    bytes_in bigint not null default 0,
    bytes_out bigint not null default 0,
    total_bytes bigint generated always as (bytes_in + bytes_out) stored,
    last_score_recalc_at timestamptz,
    updated_at timestamptz not null default now()
);

create table if not exists proxy_health_windows (
    id bigserial primary key,
    proxy_id bigint not null references proxies(id) on delete cascade,
    window_type text not null check (window_type in ('last5','last10','hour','day')),
    sample_count integer not null default 0,
    success_count integer not null default 0,
    success_rate numeric(8,5),
    avg_latency_ms numeric(12,3),
    min_latency_ms numeric(12,3),
    max_latency_ms numeric(12,3),
    latency_jitter_ms numeric(12,3),
    flap_score numeric(12,5),
    quarantine_score numeric(12,5),
    calculated_at timestamptz not null default now(),
    unique(proxy_id, window_type)
);

create table if not exists sessions (
    id uuid primary key default gen_random_uuid(),
    account_id bigint not null references accounts(id),
    client_ip inet not null,
    client_login text not null,
    assigned_proxy_id bigint references proxies(id),
    sticky_proxy_id bigint references proxies(id),
    strategy_variant text not null check (strategy_variant in ('A','B')),
    status text not null default 'active' check (status in ('active','closed','killed','error')),
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    last_activity_at timestamptz not null default now(),
    connections_count integer not null default 0,
    active_connections_count integer not null default 0,
    bytes_in bigint not null default 0,
    bytes_out bigint not null default 0,
    total_bytes bigint generated always as (bytes_in + bytes_out) stored,
    avg_speed_in_mbps numeric(12,3),
    avg_speed_out_mbps numeric(12,3),
    avg_speed_total_mbps numeric(12,3),
    kill_reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists session_connections (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(id) on delete cascade,
    proxy_id bigint references proxies(id),
    target_host text not null,
    target_port integer not null check (target_port > 0 and target_port <= 65535),
    state text not null default 'open' check (state in ('open','closed','failed','killed')),
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    last_activity_at timestamptz not null default now(),
    bytes_in bigint not null default 0,
    bytes_out bigint not null default 0,
    total_bytes bigint generated always as (bytes_in + bytes_out) stored,
    avg_speed_mbps numeric(12,3),
    close_reason text
);

create table if not exists routing_events (
    id bigserial primary key,
    session_id uuid references sessions(id) on delete cascade,
    old_proxy_id bigint references proxies(id),
    new_proxy_id bigint references proxies(id),
    event_type text not null check (event_type in ('initial_assign','sticky_reuse','reroute_new_connections','proxy_offline','proxy_quarantine','manual_kill','strategy_switch')),
    reason text,
    strategy_variant text check (strategy_variant in ('A','B')),
    created_at timestamptz not null default now()
);

create table if not exists traffic_rollups (
    id bigserial primary key,
    scope_type text not null check (scope_type in ('proxy','account','country','global')),
    scope_id text not null,
    bucket_type text not null check (bucket_type in ('hour','day')),
    bucket_start timestamptz not null,
    sessions_count integer not null default 0,
    connections_count integer not null default 0,
    bytes_in bigint not null default 0,
    bytes_out bigint not null default 0,
    total_bytes bigint generated always as (bytes_in + bytes_out) stored,
    avg_speed_mbps numeric(12,3),
    unique(scope_type, scope_id, bucket_type, bucket_start)
);

create table if not exists account_aggregates (
    account_id bigint primary key references accounts(id) on delete cascade,
    active_sessions integer not null default 0,
    total_sessions bigint not null default 0,
    total_connections bigint not null default 0,
    bytes_in bigint not null default 0,
    bytes_out bigint not null default 0,
    total_bytes bigint generated always as (bytes_in + bytes_out) stored,
    avg_speed_mbps numeric(12,3),
    updated_at timestamptz not null default now()
);

create table if not exists country_aggregates (
    country_code text primary key,
    total_proxies integer not null default 0,
    working_proxies integer not null default 0,
    online_proxies integer not null default 0,
    degraded_proxies integer not null default 0,
    quarantined_proxies integer not null default 0,
    avg_latency_day_ms numeric(12,3),
    avg_download_day_mbps numeric(12,3),
    avg_upload_day_mbps numeric(12,3),
    active_sessions integer not null default 0,
    bytes_in bigint not null default 0,
    bytes_out bigint not null default 0,
    total_bytes bigint generated always as (bytes_in + bytes_out) stored,
    updated_at timestamptz not null default now()
);

create table if not exists system_settings (
    key text primary key,
    value jsonb not null,
    updated_at timestamptz not null default now()
);

create table if not exists scheduler_state (
    worker_name text primary key,
    status text not null check (status in ('idle','running','paused','error')),
    last_started_at timestamptz,
    last_finished_at timestamptz,
    last_cursor text,
    pause_reason text,
    updated_at timestamptz not null default now()
);

create table if not exists audit_logs (
    id bigserial primary key,
    actor_type text not null check (actor_type in ('admin','system')),
    actor_id text,
    action text not null,
    target_type text,
    target_id text,
    payload jsonb,
    created_at timestamptz not null default now()
);
