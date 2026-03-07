"""Auth Agent: SOCKS5 connect + TCP connect to 8.8.8.8:53 through proxy."""

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('auth_agent')

BATCH_SIZE = 2000
ATTEMPTS_PER_PROXY = 5
ATTEMPT_DELAY = 0.5  # seconds between attempts
TARGET_HOST = '8.8.8.8'
TARGET_PORT = 53
CONNECT_TIMEOUT = 8
MAX_WORKERS = 50


def run_auth_cycle():
    """Full cycle: check ALL enabled proxies (skip only disabled/blocked)."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, host(host) AS host, port, auth_username, auth_password
            FROM proxies
            WHERE is_enabled = true AND status NOT IN ('disabled', 'blocked')
            ORDER BY coalesce(last_auth_at, last_ping_at, first_seen_at) ASC NULLS FIRST
        """)
        all_proxies = cur.fetchall()

    if not all_proxies:
        log.info('no proxies to auth-check')
        return

    total = len(all_proxies)
    for batch_start in range(0, total, BATCH_SIZE):
        batch = all_proxies[batch_start:batch_start + BATCH_SIZE]
        _auth_batch(batch)

    log.info('auth cycle complete total=%d', total)


def _auth_batch(batch: list[dict]):
    now = datetime.now(timezone.utc)
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_check_proxy, p): p for p in batch}
        for future in as_completed(futures):
            proxy = futures[future]
            try:
                data = future.result()
            except Exception as exc:
                log.error('auth check proxy_id=%s error: %s', proxy['id'], exc)
                data = {'ok': 0, 'fail': ATTEMPTS_PER_PROXY, 'latencies': [], 'error': str(exc)}
            results.append((proxy, data))

    with get_conn() as conn, conn.cursor() as cur:
        for proxy, data in results:
            ok = data['ok']
            fail = data['fail']
            lats = data['latencies']
            is_auth_ok = ok > 0
            avg_lat = sum(lats) / len(lats) if lats else None
            min_lat = min(lats) if lats else None
            max_lat = max(lats) if lats else None

            cur.execute("""
                INSERT INTO proxy_auth_checks(proxy_id, attempts, success_count,
                    fail_count, avg_latency_ms, min_latency_ms, max_latency_ms,
                    is_auth_ok, error_code, checked_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                proxy['id'], ATTEMPTS_PER_PROXY, ok, fail,
                avg_lat, min_lat, max_lat, is_auth_ok,
                data.get('error'), now,
            ))

            new_status = 'online' if is_auth_ok else 'offline'
            cur.execute("""
                UPDATE proxies SET
                    status = %s,
                    last_auth_at = %s,
                    last_checked_at = %s,
                    last_success_at = CASE WHEN %s THEN %s ELSE last_success_at END,
                    last_failure_at = CASE WHEN NOT %s THEN %s ELSE last_failure_at END
                WHERE id = %s
            """, (new_status, now, now, is_auth_ok, now, is_auth_ok, now, proxy['id']))

            # Update current day stats
            sum_ms = sum(lats)
            cur.execute("""
                INSERT INTO proxy_current_day_stats (proxy_id, auth_total_ok, auth_total_error,
                    auth_sum_ms, auth_check_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (proxy_id) DO UPDATE SET
                    auth_total_ok = proxy_current_day_stats.auth_total_ok + EXCLUDED.auth_total_ok,
                    auth_total_error = proxy_current_day_stats.auth_total_error + EXCLUDED.auth_total_error,
                    auth_sum_ms = proxy_current_day_stats.auth_sum_ms + EXCLUDED.auth_sum_ms,
                    auth_check_count = proxy_current_day_stats.auth_check_count + EXCLUDED.auth_check_count,
                    updated_at = now()
            """, (proxy['id'], ok, fail, sum_ms, len(lats)))

        conn.commit()

    online = sum(1 for _, d in results if d['ok'] > 0)
    log.info('auth batch complete size=%d online=%d', len(batch), online)


def _check_proxy(proxy: dict) -> dict:
    """Check single proxy: 5 TCP connects to 8.8.8.8:53 with 0.5s delay."""
    ok = 0
    fail = 0
    latencies = []
    last_error = None

    for attempt in range(ATTEMPTS_PER_PROXY):
        if attempt > 0:
            time.sleep(ATTEMPT_DELAY)
        success, lat_ms, err = socks5_tcp_connect(
            proxy['host'], proxy['port'],
            proxy.get('auth_username'), proxy.get('auth_password'),
            TARGET_HOST, TARGET_PORT,
        )
        if success:
            ok += 1
            if lat_ms is not None:
                latencies.append(lat_ms)
        else:
            fail += 1
            last_error = err

    return {'ok': ok, 'fail': fail, 'latencies': latencies, 'error': last_error}


def socks5_tcp_connect(proxy_host, proxy_port, username, password,
                       target_host, target_port):
    """SOCKS5 handshake + CONNECT to target. Returns (ok, latency_ms, error)."""
    start = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(CONNECT_TIMEOUT)
    try:
        s.connect((proxy_host, int(proxy_port)))

        # SOCKS5 greeting
        methods = [0x02] if username else [0x00]
        s.sendall(bytes([0x05, len(methods)] + methods))
        resp = s.recv(2)
        if len(resp) < 2 or resp[0] != 0x05 or resp[1] == 0xFF:
            return False, None, 'handshake_failed'

        # Auth subneg
        if resp[1] == 0x02:
            u = (username or '').encode()
            p = (password or '').encode()
            s.sendall(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
            auth_resp = s.recv(2)
            if len(auth_resp) < 2 or auth_resp[1] != 0x00:
                return False, None, 'auth_failed'

        # CONNECT to target
        target_ip_bytes = socket.inet_aton(target_host)
        port_bytes = int(target_port).to_bytes(2, 'big')
        s.sendall(bytes([0x05, 0x01, 0x00, 0x01]) + target_ip_bytes + port_bytes)
        connect_resp = s.recv(10)
        if len(connect_resp) < 2 or connect_resp[1] != 0x00:
            code = connect_resp[1] if len(connect_resp) > 1 else 0xFF
            return False, None, f'connect_refused_{code}'

        latency = int((time.perf_counter() - start) * 1000)
        return True, latency, None

    except socket.timeout:
        return False, None, 'timeout'
    except ConnectionRefusedError:
        return False, None, 'connection_refused'
    except Exception as exc:
        return False, None, exc.__class__.__name__
    finally:
        try:
            s.close()
        except Exception:
            pass


def auth_single(proxy: dict) -> tuple[bool, float | None]:
    """Single auth check for session monitor. Returns (ok, latency_ms)."""
    ok, lat, _ = socks5_tcp_connect(
        proxy['host'], int(proxy['port']),
        proxy.get('auth_username'), proxy.get('auth_password'),
        TARGET_HOST, TARGET_PORT,
    )
    return ok, lat
