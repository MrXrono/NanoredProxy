import socket
import time
import uuid
from datetime import datetime, timezone

from workers.common.db import get_conn
from psycopg.errors import DeadlockDetected
from workers.common.logging import get_logger
from workers.common.runtime import get_setting, set_worker_state

log = get_logger('availability')


def check_proxy(proxy: dict) -> tuple[bool, int | None, str | None]:
    start = time.perf_counter()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(8)
    try:
        s.connect((proxy['host'], proxy['port']))
        methods = [0x00]
        if proxy.get('auth_username'):
            methods = [0x02]
        s.sendall(bytes([0x05, len(methods), *methods]))
        resp = s.recv(2)
        if len(resp) < 2 or resp[0] != 0x05 or resp[1] == 0xFF:
            return False, None, 'handshake_failed'
        if resp[1] == 0x02:
            u = (proxy.get('auth_username') or '').encode()
            p = (proxy.get('auth_password') or '').encode()
            s.sendall(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
            auth_resp = s.recv(2)
            if len(auth_resp) < 2 or auth_resp[1] != 0x00:
                return False, None, 'auth_failed'
        latency = int((time.perf_counter() - start) * 1000)
        return True, latency, None
    except Exception as exc:
        return False, None, exc.__class__.__name__
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    set_worker_state('availability_checker', 'running')
    while True:
        batch_size = int(get_setting('quarantine_batch_size', {'value': 10}).get('value', 10))
        pause_seconds = int(get_setting('quarantine_pause_seconds', {'value': 2}).get('value', 2))
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select id, host(host) as host, port, auth_username, auth_password, latency_threshold_ms from proxies where is_enabled=true order by coalesce(last_checked_at, first_seen_at) asc nulls first limit %s", (batch_size,))
            batch = cur.fetchall()
            if not batch:
                set_worker_state('availability_checker', 'idle')
                time.sleep(5)
                set_worker_state('availability_checker', 'running')
                continue
            batch_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            results = []
            for idx, proxy in enumerate(batch, start=1):
                success, latency_ms, error_code = check_proxy(proxy)
                status = 'online' if success and latency_ms is not None and latency_ms <= proxy['latency_threshold_ms'] else 'degraded' if success else 'offline'
                results.append((proxy, idx, success, latency_ms, error_code, status))
        for proxy, idx, success, latency_ms, error_code, status in results:
            for attempt in range(3):
                try:
                    with get_conn() as conn2, conn2.cursor() as cur2:
                        cur2.execute(
                            """insert into proxy_checks(proxy_id, batch_id, check_no_in_window, success, tcp_connect_ok, socks_handshake_ok, auth_ok, latency_ms, error_code, checked_at)
                               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (proxy['id'], batch_id, idx, success, success, success, success, latency_ms, error_code, now),
                        )
                        cur2.execute(
                            """update proxies set status=%s, last_checked_at=%s, last_success_at=case when %s then %s else last_success_at end,
                               last_failure_at=case when not %s then %s else last_failure_at end, last_error_code=%s where id=%s""",
                            (status, now, success, now, success, now, error_code, proxy['id']),
                        )
                        conn2.commit()
                    break
                except DeadlockDetected:
                    if attempt < 2:
                        time.sleep(0.5)
                    else:
                        log.warning('deadlock on proxy_id=%s after 3 retries', proxy['id'])
        log.info('availability batch complete size=%s', len(batch))
        time.sleep(pause_seconds)


if __name__ == '__main__':
    main()
