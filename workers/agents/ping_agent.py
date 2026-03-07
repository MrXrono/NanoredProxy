"""Ping Agent: ICMP batch ping using fping, 500 IPs x 5 packets."""

import re
import subprocess
import time
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('ping_agent')

BATCH_SIZE = 2000
PACKETS_PER_IP = 5
BATCH_PAUSE_SECONDS = 2


def run_ping_cycle():
    """Full cycle: ping ALL enabled proxies in batches of 500."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, host(host) AS host
            FROM proxies
            WHERE is_enabled = true AND status != 'blocked'
            ORDER BY coalesce(last_ping_at, first_seen_at) ASC NULLS FIRST
        """)
        all_proxies = cur.fetchall()

    if not all_proxies:
        log.info('no proxies to ping')
        return

    total = len(all_proxies)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = all_proxies[batch_start:batch_start + BATCH_SIZE]
        _ping_batch(batch)

        if batch_start + BATCH_SIZE < total:
            time.sleep(BATCH_PAUSE_SECONDS)

    log.info('ping cycle complete total=%d', total)


def _ping_batch(batch: list[dict]):
    ip_to_proxy = {p['host']: p for p in batch}
    ips = list(ip_to_proxy.keys())

    try:
        proc = subprocess.run(
            ['fping', '-c', str(PACKETS_PER_IP), '-q', '-t', '2000'] + ips,
            capture_output=True, text=True, timeout=120,
        )
        output = proc.stderr  # fping writes summary to stderr
    except subprocess.TimeoutExpired:
        log.warning('fping batch timed out, size=%d', len(batch))
        output = ''
    except Exception as exc:
        log.error('fping error: %s', exc)
        output = ''

    results = _parse_fping(output, ip_to_proxy)
    now = datetime.now(timezone.utc)

    with get_conn() as conn, conn.cursor() as cur:
        for proxy_id, d in results.items():
            # Insert check record
            cur.execute("""
                INSERT INTO proxy_ping_checks(proxy_id, packets_sent, packets_ok,
                    packets_lost, avg_rtt_ms, min_rtt_ms, max_rtt_ms, is_alive, checked_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                proxy_id, PACKETS_PER_IP, d['rcv'], d['lost'],
                d['avg'], d['min'], d['max'], d['rcv'] > 0, now,
            ))

            # Update last_ping_at only (status managed by auth agent)
            cur.execute("""
                UPDATE proxies SET last_ping_at = %s
                WHERE id = %s
            """, (now, proxy_id))

            # Update current day stats
            ok = d['rcv']
            err = d['lost']
            sum_ms = (d['avg'] or 0) * ok if d['avg'] else 0
            cur.execute("""
                INSERT INTO proxy_current_day_stats (proxy_id, ping_total_ok, ping_total_error,
                    ping_sum_ms, ping_check_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (proxy_id) DO UPDATE SET
                    ping_total_ok = proxy_current_day_stats.ping_total_ok + EXCLUDED.ping_total_ok,
                    ping_total_error = proxy_current_day_stats.ping_total_error + EXCLUDED.ping_total_error,
                    ping_sum_ms = proxy_current_day_stats.ping_sum_ms + EXCLUDED.ping_sum_ms,
                    ping_check_count = proxy_current_day_stats.ping_check_count + EXCLUDED.ping_check_count,
                    updated_at = now()
            """, (proxy_id, ok, err, sum_ms, ok))

        conn.commit()

    log.info('ping batch complete size=%d alive=%d',
             len(batch), sum(1 for d in results.values() if d['rcv'] > 0))


def _parse_fping(output: str, ip_to_proxy: dict) -> dict:
    """Parse fping -c N -q stderr output.
    Format: 1.2.3.4 : xmt/rcv/%loss = 5/3/40%, min/avg/max = 12.3/15.6/20.1
    """
    results = {}
    for ip, proxy in ip_to_proxy.items():
        results[proxy['id']] = {'rcv': 0, 'lost': PACKETS_PER_IP, 'avg': None, 'min': None, 'max': None}

    for line in (output or '').strip().splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        ip = line.split(':')[0].strip()
        if ip not in ip_to_proxy:
            continue
        pid = ip_to_proxy[ip]['id']

        m = re.search(r'xmt/rcv/%loss\s*=\s*(\d+)/(\d+)/(\d+)%', line)
        if not m:
            continue
        xmt, rcv = int(m.group(1)), int(m.group(2))

        avg_ms = min_ms = max_ms = None
        m2 = re.search(r'min/avg/max\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)', line)
        if m2:
            min_ms, avg_ms, max_ms = float(m2.group(1)), float(m2.group(2)), float(m2.group(3))

        results[pid] = {'rcv': rcv, 'lost': xmt - rcv, 'avg': avg_ms, 'min': min_ms, 'max': max_ms}

    return results


def ping_single(ip: str, count: int = 5) -> dict:
    """Ping a single IP, used by session monitor. Returns {rcv, lost, avg, min, max}."""
    try:
        proc = subprocess.run(
            ['fping', '-c', str(count), '-q', '-t', '2000', ip],
            capture_output=True, text=True, timeout=30,
        )
        for line in (proc.stderr or '').strip().splitlines():
            m = re.search(r'xmt/rcv/%loss\s*=\s*(\d+)/(\d+)/(\d+)%', line)
            if m:
                xmt, rcv = int(m.group(1)), int(m.group(2))
                avg_ms = None
                m2 = re.search(r'min/avg/max\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)', line)
                if m2:
                    avg_ms = float(m2.group(2))
                return {'rcv': rcv, 'lost': xmt - rcv, 'avg': avg_ms}
    except Exception:
        pass
    return {'rcv': 0, 'lost': count, 'avg': None}
