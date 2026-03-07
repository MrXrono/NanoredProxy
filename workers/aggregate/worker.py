import time
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.common.quarantine import should_quarantine
from workers.common.runtime import get_setting, set_worker_state
from workers.common.scoring import composite_score, normalize_latency, normalize_speed

log = get_logger('aggregate')


def main():
    set_worker_state('aggregate_recalculator', 'running')
    while True:
        threshold = float(get_setting('latency_threshold_ms', {'value': 1500}).get('value', 1500))
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute('select id from proxies order by id asc')
            proxy_ids = [r['id'] for r in cur.fetchall()]
            now = datetime.now(timezone.utc)
            for proxy_id in proxy_ids:
                cur.execute("select count(*) total_checks, count(*) filter (where success) success_checks, avg(latency_ms) avg_latency_all from proxy_checks where proxy_id=%s", (proxy_id,))
                all_row = cur.fetchone()
                cur.execute("select count(*) total_day, count(*) filter (where success) success_day, avg(latency_ms) avg_latency_day, min(latency_ms) min_latency_day, max(latency_ms) max_latency_day from proxy_checks where proxy_id=%s and checked_at >= now() - interval '1 day'", (proxy_id,))
                day_row = cur.fetchone()
                cur.execute("select count(*) total_hour, count(*) filter (where success) success_hour, avg(latency_ms) avg_latency_hour from proxy_checks where proxy_id=%s and checked_at >= now() - interval '1 hour'", (proxy_id,))
                hour_row = cur.fetchone()
                cur.execute("select avg(download_mbps) avg_download_day, avg(upload_mbps) avg_upload_day, avg(ping_ms) avg_ping_day, avg(jitter_ms) avg_jitter_day, count(*) total_speedtests from proxy_speedtests where proxy_id=%s and started_at >= now() - interval '1 day'", (proxy_id,))
                speed_row = cur.fetchone()
                total = all_row['total_checks'] or 0
                total_day = day_row['total_day'] or 0
                total_hour = hour_row['total_hour'] or 0
                sr_all = (all_row['success_checks'] or 0) / total if total else 0.0
                sr_day = (day_row['success_day'] or 0) / total_day if total_day else 0.0
                sr_hour = (hour_row['success_hour'] or 0) / total_hour if total_hour else 0.0
                stability = max(0.0, min(1.0, (sr_all * 0.3) + (sr_day * 0.5) + (sr_hour * 0.2)))
                latency_score = normalize_latency(float(day_row['avg_latency_day']) if day_row['avg_latency_day'] is not None else None, threshold)
                speed_score = normalize_speed(float(speed_row['avg_download_day']) if speed_row['avg_download_day'] is not None else None, float(speed_row['avg_upload_day']) if speed_row['avg_upload_day'] is not None else None)
                score = composite_score(latency_score, speed_score, stability, 0.0)
                quarantine = should_quarantine(sr_day, float(day_row['avg_latency_day']) if day_row['avg_latency_day'] is not None else None, 1.0 - stability, threshold)
                cur.execute(
                    """insert into proxy_aggregates(proxy_id, avg_latency_all_ms, avg_latency_day_ms, avg_latency_hour_ms, min_latency_day_ms, max_latency_day_ms,
                       success_rate_all, success_rate_day, success_rate_hour, avg_download_day_mbps, avg_upload_day_mbps, avg_ping_day_ms, avg_jitter_day_ms,
                       total_checks, total_speedtests, total_success_checks, total_failed_checks, stability_score, composite_score, quarantine_score, last_score_recalc_at, updated_at)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict (proxy_id) do update set avg_latency_all_ms=excluded.avg_latency_all_ms, avg_latency_day_ms=excluded.avg_latency_day_ms,
                       avg_latency_hour_ms=excluded.avg_latency_hour_ms, min_latency_day_ms=excluded.min_latency_day_ms, max_latency_day_ms=excluded.max_latency_day_ms,
                       success_rate_all=excluded.success_rate_all, success_rate_day=excluded.success_rate_day, success_rate_hour=excluded.success_rate_hour,
                       avg_download_day_mbps=excluded.avg_download_day_mbps, avg_upload_day_mbps=excluded.avg_upload_day_mbps, avg_ping_day_ms=excluded.avg_ping_day_ms,
                       avg_jitter_day_ms=excluded.avg_jitter_day_ms, total_checks=excluded.total_checks, total_speedtests=excluded.total_speedtests,
                       total_success_checks=excluded.total_success_checks, total_failed_checks=excluded.total_failed_checks, stability_score=excluded.stability_score,
                       composite_score=excluded.composite_score, quarantine_score=excluded.quarantine_score, last_score_recalc_at=excluded.last_score_recalc_at, updated_at=excluded.updated_at""",
                    (proxy_id, all_row['avg_latency_all'], day_row['avg_latency_day'], hour_row['avg_latency_hour'], day_row['min_latency_day'], day_row['max_latency_day'], sr_all, sr_day, sr_hour, speed_row['avg_download_day'], speed_row['avg_upload_day'], speed_row['avg_ping_day'], speed_row['avg_jitter_day'], total, speed_row['total_speedtests'] or 0, all_row['success_checks'] or 0, total - (all_row['success_checks'] or 0), stability, score, 1.0 - stability, now, now),
                )
                cur.execute("update proxies set is_quarantined=%s, status=case when %s then 'quarantine' when status='quarantine' and not %s then 'checking' else status end where id=%s", (quarantine, quarantine, quarantine, proxy_id))

            cur.execute("select distinct country_code from proxies where country_code is not null")
            countries = [r['country_code'] for r in cur.fetchall()]
            for cc in countries:
                cur.execute(
                    """insert into country_aggregates(country_code, total_proxies, working_proxies, online_proxies, degraded_proxies, quarantined_proxies,
                       avg_latency_day_ms, avg_download_day_mbps, avg_upload_day_mbps, active_sessions, bytes_in, bytes_out, updated_at)
                       select %s,
                           count(*),
                           count(*) filter (where p.status in ('online','degraded') and p.is_enabled=true and p.is_quarantined=false),
                           count(*) filter (where p.status='online'),
                           count(*) filter (where p.status='degraded'),
                           count(*) filter (where p.is_quarantined=true),
                           avg(pa.avg_latency_day_ms), avg(pa.avg_download_day_mbps), avg(pa.avg_upload_day_mbps),
                           (select count(*) from sessions s join accounts a on a.id=s.account_id where s.status='active' and a.country_code=%s),
                           coalesce((select sum(bytes_in) from traffic_rollups tr where tr.scope_type='country' and tr.scope_id=%s), 0),
                           coalesce((select sum(bytes_out) from traffic_rollups tr where tr.scope_type='country' and tr.scope_id=%s), 0),
                           %s
                       from proxies p left join proxy_aggregates pa on pa.proxy_id=p.id where p.country_code=%s
                       on conflict (country_code) do update set total_proxies=excluded.total_proxies, working_proxies=excluded.working_proxies,
                       online_proxies=excluded.online_proxies, degraded_proxies=excluded.degraded_proxies, quarantined_proxies=excluded.quarantined_proxies,
                       avg_latency_day_ms=excluded.avg_latency_day_ms, avg_download_day_mbps=excluded.avg_download_day_mbps,
                       avg_upload_day_mbps=excluded.avg_upload_day_mbps, active_sessions=excluded.active_sessions, bytes_in=excluded.bytes_in,
                       bytes_out=excluded.bytes_out, updated_at=excluded.updated_at""",
                    (cc, cc, cc, cc, now, cc),
                )
            conn.commit()
        log.info('aggregate recompute complete')
        time.sleep(30)


if __name__ == '__main__':
    main()
