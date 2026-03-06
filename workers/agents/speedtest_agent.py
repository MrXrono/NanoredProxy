"""Speedtest Agent: Ookla speedtest via proxychains4, 1 proxy at a time."""

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('speedtest_agent')


def run_speedtest_single():
    """Check ONE proxy. Returns True if a test was run, False if nothing to do."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, host(host) AS host, port, auth_username, auth_password
            FROM proxies
            WHERE is_enabled = true AND status IN ('online', 'degraded')
            ORDER BY coalesce(last_speedtest_at, first_seen_at) ASC NULLS FIRST
            LIMIT 1
        """)
        proxy = cur.fetchone()

    if not proxy:
        return False

    result = _run_speedtest(proxy)
    now = datetime.now(timezone.utc)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO proxy_speedtests(proxy_id, started_at, finished_at, success,
                partial_success, ping_ms, jitter_ms, download_mbps, upload_mbps,
                download_ok, upload_ok, ping_ok, raw_output, error_code, error_message)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            proxy['id'], result['started_at'], result['finished_at'],
            result['success'], result['partial_success'],
            result.get('ping_ms'), result.get('jitter_ms'),
            result.get('download_mbps'), result.get('upload_mbps'),
            result.get('download_ok'), result.get('upload_ok'),
            result.get('ping_ok'), result.get('raw_output'),
            result.get('error_code'), result.get('error_message'),
        ))
        cur.execute("UPDATE proxies SET last_speedtest_at = %s WHERE id = %s",
                    (now, proxy['id']))

        # Update current day stats
        if result['success']:
            dl = result.get('download_mbps') or 0
            ul = result.get('upload_mbps') or 0
            cur.execute("""
                INSERT INTO proxy_current_day_stats (proxy_id,
                    speedtest_sum_download_mbps, speedtest_sum_upload_mbps, speedtest_count)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (proxy_id) DO UPDATE SET
                    speedtest_sum_download_mbps = proxy_current_day_stats.speedtest_sum_download_mbps + EXCLUDED.speedtest_sum_download_mbps,
                    speedtest_sum_upload_mbps = proxy_current_day_stats.speedtest_sum_upload_mbps + EXCLUDED.speedtest_sum_upload_mbps,
                    speedtest_count = proxy_current_day_stats.speedtest_count + 1,
                    updated_at = now()
            """, (proxy['id'], dl, ul))

        conn.commit()

    log.info('speedtest proxy_id=%s success=%s', proxy['id'], result['success'])
    return True


def _write_proxychains_conf(proxy: dict) -> str:
    auth = ''
    if proxy.get('auth_username'):
        auth = f" {proxy['auth_username']} {proxy['auth_password']}"
    conf = f"""strict_chain
quiet_mode
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 10000

[ProxyList]
socks5 {proxy['host']} {proxy['port']}{auth}
"""
    fd, path = tempfile.mkstemp(suffix='.conf', prefix='proxychains_')
    with os.fdopen(fd, 'w') as f:
        f.write(conf)
    return path


def _run_speedtest(proxy: dict) -> dict:
    conf_path = _write_proxychains_conf(proxy)
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            ['proxychains4', '-f', conf_path, 'speedtest',
             '--accept-license', '--accept-gdpr', '--format=json'],
            capture_output=True, text=True, timeout=180,
        )
        raw = (proc.stdout or '') + (proc.stderr or '')
        if proc.returncode != 0:
            return {'started_at': started, 'finished_at': datetime.now(timezone.utc),
                    'success': False, 'partial_success': False, 'raw_output': raw,
                    'error_code': f'rc_{proc.returncode}', 'error_message': 'speedtest failed'}

        json_str = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.startswith('{'):
                json_str = line
                break
        if not json_str:
            json_str = proc.stdout

        data = json.loads(json_str)
        ping = (data.get('ping') or {}).get('latency')
        jitter = (data.get('ping') or {}).get('jitter')
        download = (data.get('download') or {}).get('bandwidth')
        upload = (data.get('upload') or {}).get('bandwidth')

        return {
            'started_at': started, 'finished_at': datetime.now(timezone.utc),
            'success': True, 'partial_success': False,
            'ping_ms': ping, 'jitter_ms': jitter,
            'download_mbps': (download * 8 / 1_000_000) if download else None,
            'upload_mbps': (upload * 8 / 1_000_000) if upload else None,
            'download_ok': download is not None, 'upload_ok': upload is not None,
            'ping_ok': ping is not None, 'raw_output': proc.stdout,
            'error_code': None, 'error_message': None,
        }
    except subprocess.TimeoutExpired as exc:
        return {'started_at': started, 'finished_at': datetime.now(timezone.utc),
                'success': False, 'partial_success': False,
                'raw_output': exc.stdout or '', 'error_code': 'timeout',
                'error_message': 'speedtest timeout'}
    except Exception as exc:
        return {'started_at': started, 'finished_at': datetime.now(timezone.utc),
                'success': False, 'partial_success': False, 'raw_output': '',
                'error_code': exc.__class__.__name__, 'error_message': str(exc)}
    finally:
        try:
            os.unlink(conf_path)
        except OSError:
            pass
