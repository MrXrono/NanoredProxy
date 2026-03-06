"""Aggregate Agent: compute 0-600 rating from proxy_current_day_stats."""

from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.common.rating import compute_rating

log = get_logger('aggregate_agent')


def run_aggregate_cycle():
    """Recompute rating_score for all proxies and update country_aggregates."""
    now = datetime.now(timezone.utc)
    with get_conn() as conn, conn.cursor() as cur:
        # Read current day stats for all proxies
        cur.execute("""
            SELECT p.id AS proxy_id, pcd.ping_total_ok, pcd.ping_total_error,
                pcd.ping_sum_ms, pcd.ping_check_count,
                pcd.auth_total_ok, pcd.auth_total_error,
                pcd.auth_sum_ms, pcd.auth_check_count,
                pcd.speedtest_sum_download_mbps, pcd.speedtest_sum_upload_mbps,
                pcd.speedtest_count
            FROM proxies p
            LEFT JOIN proxy_current_day_stats pcd ON pcd.proxy_id = p.id
            WHERE p.is_enabled = true
            ORDER BY p.id
        """)
        rows = cur.fetchall()

        for row in rows:
            pid = row['proxy_id']
            p_ok = row['ping_total_ok'] or 0
            p_err = row['ping_total_error'] or 0
            p_cnt = row['ping_check_count'] or 0
            p_avg = float(row['ping_sum_ms']) / p_cnt if p_cnt > 0 else None

            a_ok = row['auth_total_ok'] or 0
            a_err = row['auth_total_error'] or 0
            a_cnt = row['auth_check_count'] or 0
            a_avg = float(row['auth_sum_ms']) / a_cnt if a_cnt > 0 else None

            s_cnt = row['speedtest_count'] or 0
            s_dl = float(row['speedtest_sum_download_mbps']) / s_cnt if s_cnt > 0 else None
            s_ul = float(row['speedtest_sum_upload_mbps']) / s_cnt if s_cnt > 0 else None

            p_rate = p_ok / (p_ok + p_err) if (p_ok + p_err) > 0 else None
            a_rate = a_ok / (a_ok + a_err) if (a_ok + a_err) > 0 else None

            rating = compute_rating(p_avg, p_ok, p_err, a_avg, a_ok, a_err, s_dl, s_ul)

            # Upsert proxy_aggregates (include NOT NULL columns with defaults for INSERT)
            cur.execute("""
                INSERT INTO proxy_aggregates (proxy_id, rating_score,
                    ping_avg_ms_today, ping_success_rate_today,
                    auth_avg_ms_today, auth_success_rate_today,
                    avg_download_day_mbps, avg_upload_day_mbps,
                    last_score_recalc_at, updated_at,
                    total_checks, total_speedtests, total_success_checks, total_failed_checks,
                    flap_count_day, flap_count_all,
                    current_active_sessions, current_active_connections,
                    total_sessions, total_connections, bytes_in, bytes_out)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                ON CONFLICT (proxy_id) DO UPDATE SET
                    rating_score = EXCLUDED.rating_score,
                    ping_avg_ms_today = EXCLUDED.ping_avg_ms_today,
                    ping_success_rate_today = EXCLUDED.ping_success_rate_today,
                    auth_avg_ms_today = EXCLUDED.auth_avg_ms_today,
                    auth_success_rate_today = EXCLUDED.auth_success_rate_today,
                    avg_download_day_mbps = EXCLUDED.avg_download_day_mbps,
                    avg_upload_day_mbps = EXCLUDED.avg_upload_day_mbps,
                    last_score_recalc_at = EXCLUDED.last_score_recalc_at,
                    updated_at = EXCLUDED.updated_at
            """, (pid, rating, p_avg, p_rate, a_avg, a_rate, s_dl, s_ul, now, now))

            # Update rating in current day stats
            cur.execute("""
                UPDATE proxy_current_day_stats SET rating_score = %s, updated_at = now()
                WHERE proxy_id = %s
            """, (rating, pid))

        # Recompute country_aggregates
        cur.execute("SELECT DISTINCT country_code FROM proxies WHERE country_code IS NOT NULL")
        countries = [r['country_code'] for r in cur.fetchall()]
        for cc in countries:
            cur.execute("""
                INSERT INTO country_aggregates(country_code, total_proxies, working_proxies,
                    online_proxies, degraded_proxies, quarantined_proxies,
                    avg_latency_day_ms, avg_download_day_mbps, avg_upload_day_mbps,
                    active_sessions, bytes_in, bytes_out, updated_at)
                SELECT %s,
                    count(*),
                    count(*) FILTER (WHERE p.status IN ('online','degraded') AND p.is_enabled AND NOT p.is_quarantined),
                    count(*) FILTER (WHERE p.status='online'),
                    count(*) FILTER (WHERE p.status='degraded'),
                    count(*) FILTER (WHERE p.is_quarantined),
                    avg(pa.ping_avg_ms_today), avg(pa.avg_download_day_mbps), avg(pa.avg_upload_day_mbps),
                    0, 0, 0, %s
                FROM proxies p LEFT JOIN proxy_aggregates pa ON pa.proxy_id = p.id
                WHERE p.country_code = %s
                ON CONFLICT (country_code) DO UPDATE SET
                    total_proxies = EXCLUDED.total_proxies,
                    working_proxies = EXCLUDED.working_proxies,
                    online_proxies = EXCLUDED.online_proxies,
                    degraded_proxies = EXCLUDED.degraded_proxies,
                    quarantined_proxies = EXCLUDED.quarantined_proxies,
                    avg_latency_day_ms = EXCLUDED.avg_latency_day_ms,
                    avg_download_day_mbps = EXCLUDED.avg_download_day_mbps,
                    avg_upload_day_mbps = EXCLUDED.avg_upload_day_mbps,
                    updated_at = EXCLUDED.updated_at
            """, (cc, now, cc))

        conn.commit()

    log.info('aggregate cycle complete proxies=%d countries=%d', len(rows), len(countries))
