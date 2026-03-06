import json
import os
import subprocess
import time
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.common.runtime import active_sessions_count, get_setting, set_worker_state

log = get_logger('speedtest')


def proxy_url(proxy: dict) -> str:
    if proxy.get('auth_username'):
        return f"socks5://{proxy['auth_username']}:{proxy['auth_password']}@{proxy['host']}:{proxy['port']}"
    return f"socks5://{proxy['host']}:{proxy['port']}"


def run_speedtest(proxy: dict) -> dict:
    env = os.environ.copy()
    env['ALL_PROXY'] = proxy_url(proxy)
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(['speedtest', '--accept-license', '--accept-gdpr', '--format=json'], capture_output=True, text=True, timeout=180, env=env)
        raw = (proc.stdout or '') + (proc.stderr or '')
        if proc.returncode != 0:
            return {'started_at': started, 'finished_at': datetime.now(timezone.utc), 'success': False, 'partial_success': False, 'raw_output': raw, 'error_code': f'rc_{proc.returncode}', 'error_message': 'speedtest failed'}
        data = json.loads(proc.stdout)
        ping = ((data.get('ping') or {}).get('latency'))
        jitter = ((data.get('ping') or {}).get('jitter'))
        download = ((data.get('download') or {}).get('bandwidth'))
        upload = ((data.get('upload') or {}).get('bandwidth'))
        return {
            'started_at': started,
            'finished_at': datetime.now(timezone.utc),
            'success': True,
            'partial_success': False,
            'ping_ms': ping,
            'jitter_ms': jitter,
            'download_mbps': (download * 8 / 1_000_000) if download is not None else None,
            'upload_mbps': (upload * 8 / 1_000_000) if upload is not None else None,
            'download_ok': download is not None,
            'upload_ok': upload is not None,
            'ping_ok': ping is not None,
            'raw_output': proc.stdout,
            'error_code': None,
            'error_message': None,
        }
    except subprocess.TimeoutExpired as exc:
        return {'started_at': started, 'finished_at': datetime.now(timezone.utc), 'success': False, 'partial_success': False, 'raw_output': exc.stdout or '', 'error_code': 'timeout', 'error_message': 'speedtest timeout'}
    except Exception as exc:
        return {'started_at': started, 'finished_at': datetime.now(timezone.utc), 'success': False, 'partial_success': False, 'raw_output': '', 'error_code': exc.__class__.__name__, 'error_message': str(exc)}


def main():
    set_worker_state('speedtest_runner', 'running')
    while True:
        pause_between = int(get_setting('speedtest_pause_between_tests_minutes', {'value': 5}).get('value', 5)) * 60
        resume_after_idle = int(get_setting('speedtest_resume_after_idle_minutes', {'value': 10}).get('value', 10)) * 60
        if active_sessions_count() > 0:
            log.info('active sessions detected, pausing speedtest')
            set_worker_state('speedtest_runner', 'paused', 'active sessions')
            while active_sessions_count() > 0:
                time.sleep(5)
            time.sleep(resume_after_idle)
            set_worker_state('speedtest_runner', 'running')
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select id, host(host) as host, port, auth_username, auth_password from proxies where is_enabled=true and status in ('online','degraded') order by coalesce(last_speedtest_at, first_seen_at) asc nulls first limit 1")
            proxy = cur.fetchone()
            if not proxy:
                time.sleep(30)
                continue
        result = run_speedtest(proxy)
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """insert into proxy_speedtests(proxy_id, started_at, finished_at, success, partial_success, ping_ms, jitter_ms, download_mbps, upload_mbps, download_ok, upload_ok, ping_ok, raw_output, error_code, error_message)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (proxy['id'], result['started_at'], result['finished_at'], result['success'], result['partial_success'], result.get('ping_ms'), result.get('jitter_ms'), result.get('download_mbps'), result.get('upload_mbps'), result.get('download_ok'), result.get('upload_ok'), result.get('ping_ok'), result.get('raw_output'), result.get('error_code'), result.get('error_message')),
            )
            cur.execute("update proxies set last_speedtest_at=%s where id=%s", (datetime.now(timezone.utc), proxy['id']))
            conn.commit()
        log.info('speedtest proxy_id=%s success=%s', proxy['id'], result['success'])
        time.sleep(pause_between)


if __name__ == '__main__':
    main()
