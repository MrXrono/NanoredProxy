"""Orchestrator: sequential agent execution with priority queue, session freeze, and monitoring.

Startup schedule:
  t+60s:   Ping Agent
  t+300s:  Auth Agent
  t+420s:  Speedtest Agent
  t+600s:  Geo Agent

Normal cycle (every 10 min):
  Ping(full) -> Auth(full) -> Speedtest(1 at a time, yields) -> Aggregate -> Geo -> Reconcile

Session active:
  - Queue frozen
  - Session monitor runs (ping+auth assigned+fallback)
  - After disconnect: 2min cooldown, then resume queue

Priority: Ping > Auth > Geo > Speedtest
"""

import time
import threading
from datetime import datetime, timezone

from workers.common.logging import get_logger
from workers.common.runtime import set_worker_state, active_sessions_count
from workers.agents.ping_agent import run_ping_cycle
from workers.agents.auth_agent import run_auth_cycle
from workers.agents.speedtest_agent import run_speedtest_single
from workers.agents.aggregate_agent import run_aggregate_cycle
from workers.agents.geo_agent import run_geo_cycle
from workers.agents.reconcile_agent import run_reconcile_cycle
from workers.agents.daily_rollover import check_and_rollover
from workers.agents.session_monitor import (
    SessionMonitor, get_active_sessions, get_fallback_proxy,
)

log = get_logger('orchestrator')

CYCLE_INTERVAL = 600  # 10 minutes
STARTUP_PING_DELAY = 60
STARTUP_AUTH_DELAY = 300
STARTUP_SPEEDTEST_DELAY = 420
STARTUP_GEO_DELAY = 600
SESSION_COOLDOWN = 120  # 2 minutes after disconnect


class Orchestrator:
    def __init__(self):
        self.monitor = SessionMonitor()
        self._monitored_sessions: set[str] = set()
        self._frozen = False
        self._startup_done = False

    def run(self):
        set_worker_state('orchestrator', 'running')
        start_time = time.monotonic()
        log.info('orchestrator started, waiting for startup schedule...')

        # ---- Startup phase ----
        self._wait_until(start_time + STARTUP_PING_DELAY)
        if self._check_sessions():
            self._wait_for_session_end()

        log.info('startup: running initial Ping Agent')
        set_worker_state('ping_agent', 'running')
        run_ping_cycle()
        set_worker_state('ping_agent', 'idle')

        self._wait_until(start_time + STARTUP_AUTH_DELAY)
        if self._check_sessions():
            self._wait_for_session_end()

        log.info('startup: running initial Auth Agent')
        set_worker_state('auth_agent', 'running')
        run_auth_cycle()
        set_worker_state('auth_agent', 'idle')

        # Aggregate after first ping+auth to compute initial ratings
        log.info('startup: running initial Aggregate')
        run_aggregate_cycle()

        self._wait_until(start_time + STARTUP_SPEEDTEST_DELAY)
        if self._check_sessions():
            self._wait_for_session_end()

        log.info('startup: Speedtest Agent ready')

        self._wait_until(start_time + STARTUP_GEO_DELAY)
        if self._check_sessions():
            self._wait_for_session_end()

        log.info('startup: running initial Geo Agent')
        run_geo_cycle()

        run_reconcile_cycle()
        self._startup_done = True

        # ---- Main loop ----
        log.info('startup complete, entering main loop')
        while True:
            cycle_start = time.monotonic()

            # Daily rollover check
            try:
                check_and_rollover()
            except Exception as exc:
                log.error('daily rollover error: %s', exc)

            # ---- Ping Agent (full cycle) ----
            if self._check_sessions():
                self._wait_for_session_end()
            log.info('queue: Ping Agent')
            set_worker_state('ping_agent', 'running')
            try:
                run_ping_cycle()
            except Exception as exc:
                log.error('ping agent error: %s', exc)
            set_worker_state('ping_agent', 'idle')

            # ---- Auth Agent (full cycle) ----
            if self._check_sessions():
                self._wait_for_session_end()
            log.info('queue: Auth Agent')
            set_worker_state('auth_agent', 'running')
            try:
                run_auth_cycle()
            except Exception as exc:
                log.error('auth agent error: %s', exc)
            set_worker_state('auth_agent', 'idle')

            # ---- Aggregate (compute ratings) ----
            try:
                run_aggregate_cycle()
            except Exception as exc:
                log.error('aggregate error: %s', exc)

            # ---- Speedtest Agent (1 at a time, yields to queue) ----
            speedtest_count = 0
            speedtest_deadline = cycle_start + CYCLE_INTERVAL - 120  # stop 2min before cycle end
            while time.monotonic() < speedtest_deadline:
                if self._check_sessions():
                    self._wait_for_session_end()
                    break  # after session end + cooldown, skip rest of speedtest this cycle

                # Check if higher-priority agent is due (ping/auth run every 10min = once per cycle)
                # In this implementation they already ran, so speedtest has remaining time

                set_worker_state('speedtest_agent', 'running')
                try:
                    did_work = run_speedtest_single()
                except Exception as exc:
                    log.error('speedtest error: %s', exc)
                    did_work = False
                set_worker_state('speedtest_agent', 'idle')

                if not did_work:
                    break  # no more proxies to test
                speedtest_count += 1

                # Brief pause between speedtest runs (ookla takes ~2min anyway)
                time.sleep(5)

            if speedtest_count > 0:
                log.info('speedtest cycle: tested %d proxies', speedtest_count)

            # ---- Geo Agent ----
            if self._check_sessions():
                self._wait_for_session_end()
            try:
                run_geo_cycle()
            except Exception as exc:
                log.error('geo error: %s', exc)

            # ---- Reconcile Agent ----
            try:
                run_reconcile_cycle()
            except Exception as exc:
                log.error('reconcile error: %s', exc)

            # ---- Wait for next cycle ----
            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0, CYCLE_INTERVAL - elapsed)
            if sleep_time > 0:
                log.info('cycle complete in %.0fs, sleeping %.0fs', elapsed, sleep_time)
                set_worker_state('orchestrator', 'idle')
                # Sleep in small intervals to check for sessions
                remaining = sleep_time
                while remaining > 0:
                    chunk = min(remaining, 5)
                    time.sleep(chunk)
                    remaining -= chunk
                    if self._check_sessions():
                        self._wait_for_session_end()
            set_worker_state('orchestrator', 'running')

    def _check_sessions(self) -> bool:
        """Check if there are active SOCKS5 sessions. Start/stop monitoring."""
        count = active_sessions_count()
        if count > 0:
            self._start_session_monitoring()
            return True
        else:
            self._stop_session_monitoring()
            return False

    def _start_session_monitoring(self):
        """Start monitoring threads for all active sessions."""
        sessions = get_active_sessions()
        for s in sessions:
            sid = str(s['session_id'])
            if sid not in self._monitored_sessions:
                assigned = {
                    'id': s['assigned_proxy_id'],
                    'host': s['host'],
                    'port': s['port'],
                    'auth_username': s.get('auth_username'),
                    'auth_password': s.get('auth_password'),
                }
                fallback = get_fallback_proxy(s['assigned_proxy_id'])
                self.monitor.start_monitoring(sid, assigned, fallback)
                self._monitored_sessions.add(sid)

    def _stop_session_monitoring(self):
        """Stop all monitoring if no sessions active."""
        if self._monitored_sessions:
            self.monitor.stop_all()
            self._monitored_sessions.clear()

    def _wait_for_session_end(self):
        """Freeze queue while sessions are active, then cooldown."""
        if not self._frozen:
            log.info('sessions active — freezing queue')
            set_worker_state('orchestrator', 'frozen')
            self._frozen = True

        while active_sessions_count() > 0:
            self._start_session_monitoring()
            time.sleep(5)

        self._stop_session_monitoring()
        log.info('sessions ended — cooldown %ds', SESSION_COOLDOWN)
        time.sleep(SESSION_COOLDOWN)
        self._frozen = False
        set_worker_state('orchestrator', 'running')
        log.info('cooldown complete, resuming queue')

    def _wait_until(self, target: float):
        """Sleep until target monotonic time, checking sessions."""
        while time.monotonic() < target:
            if self._check_sessions():
                self._wait_for_session_end()
            time.sleep(min(5, target - time.monotonic()))


def main():
    orchestrator = Orchestrator()
    orchestrator.run()


if __name__ == '__main__':
    main()
