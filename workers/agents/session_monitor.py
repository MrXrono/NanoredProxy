"""Session Monitor: continuous monitoring of assigned + fallback proxy during active sessions.

When a user is connected:
- Ping assigned proxy continuously
- Ping next-best proxy (fallback) continuously
- TCP connect to 8.8.8.8:53 every 5s for both
- If assigned proxy fails -> signal failover to fallback
- Stops when user disconnects
"""

import threading
import time

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.agents.ping_agent import ping_single
from workers.agents.auth_agent import auth_single

log = get_logger('session_monitor')

AUTH_CHECK_INTERVAL = 5  # seconds between TCP connect checks
PING_INTERVAL = 3  # seconds between pings
FAIL_THRESHOLD = 3  # consecutive failures before triggering failover


class SessionMonitor:
    """Monitors assigned and fallback proxies for active sessions."""

    def __init__(self):
        self._threads: dict[str, threading.Thread] = {}
        self._stop_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    @property
    def has_active_sessions(self) -> bool:
        with self._lock:
            return len(self._threads) > 0

    def start_monitoring(self, session_id: str, assigned_proxy: dict, fallback_proxy: dict | None):
        """Start monitoring threads for a session."""
        with self._lock:
            if session_id in self._threads:
                return  # already monitoring

            stop_event = threading.Event()
            self._stop_events[session_id] = stop_event

            t = threading.Thread(
                target=self._monitor_loop,
                args=(session_id, assigned_proxy, fallback_proxy, stop_event),
                daemon=True,
                name=f'monitor-{session_id[:8]}',
            )
            self._threads[session_id] = t
            t.start()
            log.info('started monitoring session=%s assigned=%s fallback=%s',
                     session_id[:8], assigned_proxy['host'],
                     fallback_proxy['host'] if fallback_proxy else 'none')

    def stop_monitoring(self, session_id: str):
        """Stop monitoring for a session."""
        with self._lock:
            ev = self._stop_events.pop(session_id, None)
            if ev:
                ev.set()
            self._threads.pop(session_id, None)
        log.info('stopped monitoring session=%s', session_id[:8])

    def stop_all(self):
        """Stop all monitoring threads."""
        with self._lock:
            for ev in self._stop_events.values():
                ev.set()
            self._stop_events.clear()
            self._threads.clear()

    def _monitor_loop(self, session_id: str, assigned: dict, fallback: dict | None,
                      stop: threading.Event):
        """Main monitoring loop for one session."""
        assigned_fails = 0
        last_auth_check = 0

        while not stop.is_set():
            now = time.monotonic()

            # Ping assigned proxy
            ping_res = ping_single(assigned['host'], count=1)
            if ping_res['rcv'] == 0:
                assigned_fails += 1
            else:
                assigned_fails = 0

            # Ping fallback if available
            if fallback:
                ping_single(fallback['host'], count=1)

            # TCP connect check every AUTH_CHECK_INTERVAL
            if now - last_auth_check >= AUTH_CHECK_INTERVAL:
                last_auth_check = now
                ok_assigned, _ = auth_single(assigned)
                if not ok_assigned:
                    assigned_fails += 1
                else:
                    assigned_fails = max(0, assigned_fails - 1)

                if fallback:
                    auth_single(fallback)

            # Failover check
            if assigned_fails >= FAIL_THRESHOLD and fallback:
                log.warning('session=%s assigned proxy %s failed %d times, triggering failover to %s',
                            session_id[:8], assigned['host'], assigned_fails, fallback['host'])
                self._trigger_failover(session_id, assigned, fallback)
                # Swap: fallback becomes assigned, get new fallback
                assigned = fallback
                fallback = self._get_next_fallback(assigned['id'])
                assigned_fails = 0

            stop.wait(PING_INTERVAL)

    def _trigger_failover(self, session_id: str, old_proxy: dict, new_proxy: dict):
        """Update session's assigned proxy in DB."""
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    UPDATE sessions SET assigned_proxy_id = %s, updated_at = now()
                    WHERE id = %s::uuid AND status = 'active'
                """, (new_proxy['id'], session_id))
                conn.commit()
            log.info('failover session=%s: %s -> %s',
                     session_id[:8], old_proxy['host'], new_proxy['host'])
        except Exception as exc:
            log.error('failover failed session=%s: %s', session_id[:8], exc)

    def _get_next_fallback(self, exclude_proxy_id: int) -> dict | None:
        """Get next best proxy as fallback (by rating_score)."""
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT p.id, host(p.host) AS host, p.port, p.auth_username, p.auth_password
                    FROM proxies p
                    LEFT JOIN proxy_aggregates pa ON pa.proxy_id = p.id
                    WHERE p.is_enabled = true AND p.status = 'online'
                        AND NOT p.is_quarantined AND p.id != %s
                    ORDER BY coalesce(pa.rating_score, 0) DESC
                    LIMIT 1
                """, (exclude_proxy_id,))
                return cur.fetchone()
        except Exception:
            return None


def get_active_sessions() -> list[dict]:
    """Get all active sessions with their assigned proxy info."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.id AS session_id, s.assigned_proxy_id,
                host(p.host) AS host, p.port, p.auth_username, p.auth_password
            FROM sessions s
            JOIN proxies p ON p.id = s.assigned_proxy_id
            WHERE s.status = 'active'
        """)
        return cur.fetchall()


def get_fallback_proxy(assigned_proxy_id: int, country_code: str | None = None) -> dict | None:
    """Get next-best proxy by rating as fallback."""
    with get_conn() as conn, conn.cursor() as cur:
        query = """
            SELECT p.id, host(p.host) AS host, p.port, p.auth_username, p.auth_password
            FROM proxies p
            LEFT JOIN proxy_aggregates pa ON pa.proxy_id = p.id
            WHERE p.is_enabled = true AND p.status = 'online'
                AND NOT p.is_quarantined AND p.id != %s
        """
        params = [assigned_proxy_id]
        if country_code:
            query += " AND p.country_code = %s"
            params.append(country_code)
        query += " ORDER BY coalesce(pa.rating_score, 0) DESC LIMIT 1"
        cur.execute(query, params)
        return cur.fetchone()
