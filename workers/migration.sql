-- NanoredProxy Worker Restructuring Migration
-- Run inside: docker compose exec -T postgres psql -U nanored -d nanoredproxy

BEGIN;

-- 1. New table: ICMP ping results
CREATE TABLE IF NOT EXISTS proxy_ping_checks (
    id          bigserial PRIMARY KEY,
    proxy_id    bigint NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
    packets_sent    smallint NOT NULL DEFAULT 5,
    packets_ok      smallint NOT NULL DEFAULT 0,
    packets_lost    smallint NOT NULL DEFAULT 0,
    avg_rtt_ms      numeric(10,2),
    min_rtt_ms      numeric(10,2),
    max_rtt_ms      numeric(10,2),
    is_alive        boolean NOT NULL DEFAULT false,
    checked_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ping_checks_proxy_id ON proxy_ping_checks(proxy_id);
CREATE INDEX IF NOT EXISTS idx_ping_checks_checked_at ON proxy_ping_checks(checked_at);

-- 2. New table: SOCKS5 auth + TCP connect results
CREATE TABLE IF NOT EXISTS proxy_auth_checks (
    id          bigserial PRIMARY KEY,
    proxy_id    bigint NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
    attempts        smallint NOT NULL DEFAULT 5,
    success_count   smallint NOT NULL DEFAULT 0,
    fail_count      smallint NOT NULL DEFAULT 0,
    avg_latency_ms  numeric(10,2),
    min_latency_ms  numeric(10,2),
    max_latency_ms  numeric(10,2),
    is_auth_ok      boolean NOT NULL DEFAULT false,
    error_code      text,
    checked_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_checks_proxy_id ON proxy_auth_checks(proxy_id);
CREATE INDEX IF NOT EXISTS idx_auth_checks_checked_at ON proxy_auth_checks(checked_at);

-- 3. New table: live counters for current day (reset at 00:00 MSK)
CREATE TABLE IF NOT EXISTS proxy_current_day_stats (
    proxy_id        bigint PRIMARY KEY REFERENCES proxies(id) ON DELETE CASCADE,
    ping_total_ok       bigint NOT NULL DEFAULT 0,
    ping_total_error    bigint NOT NULL DEFAULT 0,
    ping_sum_ms         numeric(16,2) NOT NULL DEFAULT 0,
    ping_check_count    bigint NOT NULL DEFAULT 0,
    auth_total_ok       bigint NOT NULL DEFAULT 0,
    auth_total_error    bigint NOT NULL DEFAULT 0,
    auth_sum_ms         numeric(16,2) NOT NULL DEFAULT 0,
    auth_check_count    bigint NOT NULL DEFAULT 0,
    speedtest_sum_download_mbps numeric(16,3) NOT NULL DEFAULT 0,
    speedtest_sum_upload_mbps   numeric(16,3) NOT NULL DEFAULT 0,
    speedtest_count             integer NOT NULL DEFAULT 0,
    rating_score        integer NOT NULL DEFAULT 0,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- 4. New table: daily archive (filled at 00:00 MSK rollover)
CREATE TABLE IF NOT EXISTS proxy_daily_stats (
    id              bigserial PRIMARY KEY,
    proxy_id        bigint NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
    stat_date       date NOT NULL,
    ping_total_ok       bigint NOT NULL DEFAULT 0,
    ping_total_error    bigint NOT NULL DEFAULT 0,
    ping_avg_ms         numeric(10,2),
    ping_success_rate   numeric(8,5),
    auth_total_ok       bigint NOT NULL DEFAULT 0,
    auth_total_error    bigint NOT NULL DEFAULT 0,
    auth_avg_ms         numeric(10,2),
    auth_success_rate   numeric(8,5),
    speedtest_avg_download_mbps numeric(12,3),
    speedtest_avg_upload_mbps   numeric(12,3),
    speedtest_count             integer NOT NULL DEFAULT 0,
    rating_score        integer NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE(proxy_id, stat_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_stats_proxy_date ON proxy_daily_stats(proxy_id, stat_date);

-- 5. ALTER proxies: add tracking columns
ALTER TABLE proxies ADD COLUMN IF NOT EXISTS last_ping_at timestamptz;
ALTER TABLE proxies ADD COLUMN IF NOT EXISTS last_auth_at timestamptz;

-- 6. ALTER proxy_aggregates: add rating_score
ALTER TABLE proxy_aggregates ADD COLUMN IF NOT EXISTS rating_score integer NOT NULL DEFAULT 0;
ALTER TABLE proxy_aggregates ADD COLUMN IF NOT EXISTS ping_avg_ms_today numeric(10,2);
ALTER TABLE proxy_aggregates ADD COLUMN IF NOT EXISTS ping_success_rate_today numeric(8,5);
ALTER TABLE proxy_aggregates ADD COLUMN IF NOT EXISTS auth_avg_ms_today numeric(10,2);
ALTER TABLE proxy_aggregates ADD COLUMN IF NOT EXISTS auth_success_rate_today numeric(8,5);

-- 7. Initialize proxy_current_day_stats for all existing proxies
INSERT INTO proxy_current_day_stats (proxy_id)
SELECT id FROM proxies
ON CONFLICT (proxy_id) DO NOTHING;

COMMIT;
