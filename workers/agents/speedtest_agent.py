"""Speedtest Agent: Python-based speed test via SOCKS5 proxy (no external deps).

Uses raw socket SOCKS5 handshake + HTTP to download/upload test files.
Download: Cloudflare speed test endpoint (__down?bytes=N) + fallbacks.
Upload: Cloudflare speed test endpoint (__up).
Latency: TCP CONNECT timing through proxy.
"""

import os
import socket
import ssl
import struct
import time
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('speedtest_agent')

DOWNLOAD_SIZE = 10_000_000   # 10 MB
UPLOAD_SIZE = 2_000_000      # 2 MB
DOWNLOAD_TIMEOUT = 90        # seconds
CONNECT_TIMEOUT = 15         # seconds
CHUNK_SIZE = 65536

# (host, path, port, use_tls)
DOWNLOAD_TARGETS = [
    ('speed.cloudflare.com', f'/__down?bytes={DOWNLOAD_SIZE}', 443, True),
    ('speedtest.tele2.net', '/10MB.zip', 80, False),
    ('proof.ovh.net', '/files/10Mb.dat', 80, False),
]

UPLOAD_TARGETS = [
    ('speed.cloudflare.com', '/__up', 443, True),
]

LATENCY_TARGET = ('speed.cloudflare.com', 443, True)


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

    log.info('speedtest proxy_id=%s success=%s dl=%.2f ul=%.2f ping=%.1f',
             proxy['id'], result['success'],
             result.get('download_mbps') or 0,
             result.get('upload_mbps') or 0,
             result.get('ping_ms') or 0)
    return True


# ---- SOCKS5 low-level ----

def _recv_exact(sock, n):
    """Read exactly n bytes from socket."""
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError('Connection closed during SOCKS5 handshake')
        buf += chunk
    return buf


def _socks5_connect(proxy_host, proxy_port, target_host, target_port,
                    username=None, password=None, timeout=CONNECT_TIMEOUT):
    """SOCKS5 handshake then CONNECT. Returns raw connected socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((proxy_host, int(proxy_port)))

    # Greeting
    if username and password:
        sock.sendall(b'\x05\x02\x00\x02')
    else:
        sock.sendall(b'\x05\x01\x00')

    resp = _recv_exact(sock, 2)
    if resp[0] != 0x05:
        raise ConnectionError('Not a SOCKS5 proxy')

    if resp[1] == 0x02:
        udata = (username or '').encode()
        pdata = (password or '').encode()
        sock.sendall(b'\x01' + bytes([len(udata)]) + udata
                     + bytes([len(pdata)]) + pdata)
        auth_resp = _recv_exact(sock, 2)
        if auth_resp[1] != 0x00:
            raise ConnectionError('SOCKS5 auth rejected')
    elif resp[1] == 0xFF:
        raise ConnectionError('SOCKS5 no acceptable auth')

    # CONNECT (ATYP=0x03 domain)
    domain = target_host.encode()
    sock.sendall(b'\x05\x01\x00\x03' + bytes([len(domain)]) + domain
                 + struct.pack('!H', target_port))

    hdr = _recv_exact(sock, 4)
    if hdr[1] != 0x00:
        _ERR = {1: 'general failure', 2: 'not allowed', 3: 'net unreachable',
                4: 'host unreachable', 5: 'refused', 6: 'TTL expired',
                7: 'cmd not supported', 8: 'atyp not supported'}
        raise ConnectionError(f'SOCKS5 CONNECT: {_ERR.get(hdr[1], hdr[1])}')

    # Consume bound address
    atyp = hdr[3]
    if atyp == 0x01:
        _recv_exact(sock, 4 + 2)
    elif atyp == 0x04:
        _recv_exact(sock, 16 + 2)
    elif atyp == 0x03:
        dlen = _recv_exact(sock, 1)[0]
        _recv_exact(sock, dlen + 2)
    else:
        _recv_exact(sock, 2)

    return sock


def _wrap_tls(sock, hostname):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx.wrap_socket(sock, server_hostname=hostname)


# ---- HTTP over connected socket ----

def _http_get_stream(sock, host, path):
    """HTTP GET, stream body. Returns (total_bytes, elapsed_secs, status)."""
    req = (f'GET {path} HTTP/1.1\r\n'
           f'Host: {host}\r\n'
           f'Connection: close\r\n'
           f'User-Agent: NanoredProxy/1.0\r\n'
           f'\r\n').encode()
    sock.sendall(req)

    hdr_buf = b''
    while b'\r\n\r\n' not in hdr_buf:
        chunk = sock.recv(8192)
        if not chunk:
            return 0, 0, 0
        hdr_buf += chunk

    sep = hdr_buf.index(b'\r\n\r\n') + 4
    status_line = hdr_buf[:hdr_buf.index(b'\r\n')].decode(errors='replace')
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 else 0

    body_part = hdr_buf[sep:]
    total = len(body_part)
    t0 = time.monotonic()

    while True:
        try:
            chunk = sock.recv(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
        except socket.timeout:
            break

    return total, time.monotonic() - t0, status


def _http_post_upload(sock, host, path, size):
    """HTTP POST with random payload. Returns (bytes_sent, elapsed_secs, status)."""
    payload = os.urandom(size)
    req = (f'POST {path} HTTP/1.1\r\n'
           f'Host: {host}\r\n'
           f'Connection: close\r\n'
           f'Content-Type: application/octet-stream\r\n'
           f'Content-Length: {size}\r\n'
           f'User-Agent: NanoredProxy/1.0\r\n'
           f'\r\n').encode()

    t0 = time.monotonic()
    sock.sendall(req)

    sent = 0
    while sent < size:
        end = min(sent + CHUNK_SIZE, size)
        sock.sendall(payload[sent:end])
        sent = end

    elapsed = time.monotonic() - t0

    status = 0
    try:
        sock.settimeout(5)
        resp = sock.recv(4096)
        line = resp.decode(errors='replace').split('\r\n')[0]
        status = int(line.split()[1]) if len(line.split()) >= 2 else 0
    except Exception:
        pass

    return sent, elapsed, status


# ---- Main test logic ----

def _open_tunnel(proxy, host, port, use_tls, timeout=CONNECT_TIMEOUT):
    sock = _socks5_connect(
        proxy['host'], proxy['port'], host, port,
        proxy.get('auth_username'), proxy.get('auth_password'),
        timeout=timeout,
    )
    if use_tls:
        sock = _wrap_tls(sock, host)
    sock.settimeout(DOWNLOAD_TIMEOUT)
    return sock


def _measure_latency(proxy):
    """3x TCP CONNECT through proxy -> avg ms."""
    host, port, use_tls = LATENCY_TARGET
    times = []
    for _ in range(3):
        try:
            t0 = time.monotonic()
            sock = _open_tunnel(proxy, host, port, use_tls)
            ms = (time.monotonic() - t0) * 1000
            times.append(ms)
            sock.close()
        except Exception:
            pass
        time.sleep(0.2)
    return round(sum(times) / len(times), 2) if times else None


def _measure_download(proxy):
    """Download test file through proxy. Returns (mbps, info_string)."""
    for host, path, port, use_tls in DOWNLOAD_TARGETS:
        try:
            sock = _open_tunnel(proxy, host, port, use_tls)
            total, elapsed, status = _http_get_stream(sock, host, path)
            sock.close()

            if (status == 200 or total > 500_000) and elapsed > 0.5:
                mbps = (total * 8) / (elapsed * 1_000_000)
                return round(mbps, 3), f'{host}: {total}B in {elapsed:.2f}s = {mbps:.2f} Mbps'
            else:
                log.debug('download %s: status=%s bytes=%s elapsed=%.2f', host, status, total, elapsed)
        except Exception as exc:
            log.debug('download %s failed: %s', host, exc)
    return None, 'all download targets failed'


def _measure_upload(proxy):
    """Upload random data through proxy. Returns (mbps, info_string)."""
    for host, path, port, use_tls in UPLOAD_TARGETS:
        try:
            sock = _open_tunnel(proxy, host, port, use_tls)
            sent, elapsed, status = _http_post_upload(sock, host, path, UPLOAD_SIZE)
            sock.close()

            if elapsed > 0.3:
                mbps = (sent * 8) / (elapsed * 1_000_000)
                return round(mbps, 3), f'{host}: {sent}B in {elapsed:.2f}s = {mbps:.2f} Mbps'
            else:
                log.debug('upload %s: too fast elapsed=%.3f', host, elapsed)
        except Exception as exc:
            log.debug('upload %s failed: %s', host, exc)
    return None, 'all upload targets failed'


def _run_speedtest(proxy: dict) -> dict:
    started = datetime.now(timezone.utc)
    raw_parts = []

    try:
        # 1) Latency
        ping_ms = _measure_latency(proxy)
        raw_parts.append(f'latency: {ping_ms}ms' if ping_ms else 'latency: failed')

        # 2) Download
        dl_mbps, dl_info = _measure_download(proxy)
        raw_parts.append(f'download: {dl_info}')

        # 3) Upload
        ul_mbps, ul_info = _measure_upload(proxy)
        raw_parts.append(f'upload: {ul_info}')

        success = dl_mbps is not None
        partial = success and ul_mbps is None

        return {
            'started_at': started,
            'finished_at': datetime.now(timezone.utc),
            'success': success,
            'partial_success': partial,
            'ping_ms': ping_ms,
            'jitter_ms': None,
            'download_mbps': dl_mbps,
            'upload_mbps': ul_mbps,
            'download_ok': dl_mbps is not None,
            'upload_ok': ul_mbps is not None,
            'ping_ok': ping_ms is not None,
            'raw_output': '\n'.join(raw_parts),
            'error_code': None,
            'error_message': None,
        }
    except Exception as exc:
        raw_parts.append(f'fatal: {exc}')
        return {
            'started_at': started,
            'finished_at': datetime.now(timezone.utc),
            'success': False,
            'partial_success': False,
            'raw_output': '\n'.join(raw_parts),
            'error_code': exc.__class__.__name__,
            'error_message': str(exc),
        }
