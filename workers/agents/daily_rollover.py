"""Daily Rollover: archive current day stats at 00:00 MSK and reset."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('daily_rollover')
MSK = ZoneInfo('Europe/Moscow')

_last_rollover_date = None


def check_and_rollover():
    """Check if new MSK day started. If so, archive yesterday and reset."""
    global _last_rollover_date

    today_msk = datetime.now(MSK).date()

    if _last_rollover_date is None:
        _last_rollover_date = today_msk
        return

    if _last_rollover_date >= today_msk:
        return  # same day

    yesterday = (today_msk - timedelta(days=1)).isoformat()
    log.info('daily rollover: archiving %s, resetting for %s', yesterday, today_msk)

    with get_conn() as conn, conn.cursor() as cur:
        # Archive current day stats into proxy_daily_stats
        cur.execute("""
            INSERT INTO proxy_daily_stats (
                proxy_id, stat_date,
                ping_total_ok, ping_total_error, ping_avg_ms, ping_success_rate,
                auth_total_ok, auth_total_error, auth_avg_ms, auth_success_rate,
                speedtest_avg_download_mbps, speedtest_avg_upload_mbps, speedtest_count,
                rating_score
            )
            SELECT
                proxy_id, %s::date,
                ping_total_ok, ping_total_error,
                CASE WHEN ping_check_count > 0 THEN ping_sum_ms / ping_check_count ELSE NULL END,
                CASE WHEN (ping_total_ok + ping_total_error) > 0
                     THEN ping_total_ok::numeric / (ping_total_ok + ping_total_error) ELSE NULL END,
                auth_total_ok, auth_total_error,
                CASE WHEN auth_check_count > 0 THEN auth_sum_ms / auth_check_count ELSE NULL END,
                CASE WHEN (auth_total_ok + auth_total_error) > 0
                     THEN auth_total_ok::numeric / (auth_total_ok + auth_total_error) ELSE NULL END,
                CASE WHEN speedtest_count > 0 THEN speedtest_sum_download_mbps / speedtest_count ELSE NULL END,
                CASE WHEN speedtest_count > 0 THEN speedtest_sum_upload_mbps / speedtest_count ELSE NULL END,
                speedtest_count,
                rating_score
            FROM proxy_current_day_stats
            ON CONFLICT (proxy_id, stat_date) DO UPDATE SET
                ping_total_ok = EXCLUDED.ping_total_ok,
                ping_total_error = EXCLUDED.ping_total_error,
                ping_avg_ms = EXCLUDED.ping_avg_ms,
                ping_success_rate = EXCLUDED.ping_success_rate,
                auth_total_ok = EXCLUDED.auth_total_ok,
                auth_total_error = EXCLUDED.auth_total_error,
                auth_avg_ms = EXCLUDED.auth_avg_ms,
                auth_success_rate = EXCLUDED.auth_success_rate,
                speedtest_avg_download_mbps = EXCLUDED.speedtest_avg_download_mbps,
                speedtest_avg_upload_mbps = EXCLUDED.speedtest_avg_upload_mbps,
                speedtest_count = EXCLUDED.speedtest_count,
                rating_score = EXCLUDED.rating_score
        """, (yesterday,))

        # Reset all current day counters
        cur.execute("""
            UPDATE proxy_current_day_stats SET
                ping_total_ok = 0, ping_total_error = 0,
                ping_sum_ms = 0, ping_check_count = 0,
                auth_total_ok = 0, auth_total_error = 0,
                auth_sum_ms = 0, auth_check_count = 0,
                speedtest_sum_download_mbps = 0, speedtest_sum_upload_mbps = 0,
                speedtest_count = 0,
                rating_score = 0,
                updated_at = now()
        """)

        conn.commit()

    _last_rollover_date = today_msk
    log.info('daily rollover complete for %s', yesterday)
