"""Reconcile Agent: auto-create/disable country accounts based on proxy availability."""

from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('reconcile_agent')


def run_reconcile_cycle():
    """Single pass: sync country accounts with proxy availability."""
    now = datetime.now(timezone.utc)
    with get_conn() as conn, conn.cursor() as cur:
        # Get countries with enough working proxies
        cur.execute("""
            SELECT country_code, count(*) as cnt
            FROM proxies
            WHERE is_enabled = true AND status IN ('online', 'degraded')
                AND NOT is_quarantined AND country_code IS NOT NULL
            GROUP BY country_code
            HAVING count(*) >= 2
        """)
        active_countries = {r['country_code']: r['cnt'] for r in cur.fetchall()}

        # Upsert accounts for active countries
        for cc, cnt in active_countries.items():
            cur.execute("""
                INSERT INTO accounts(username, password, account_type, country_code,
                    is_enabled, is_dynamic, min_required_working_proxies, last_reconciled_at,
                    created_at, updated_at)
                VALUES (%s, %s, 'country', %s, true, true, 2, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE SET
                    is_enabled = true,
                    last_reconciled_at = EXCLUDED.last_reconciled_at,
                    updated_at = EXCLUDED.updated_at
            """, (cc, cc, cc, now, now, now))

        # Disable accounts for countries without enough proxies
        if active_countries:
            cur.execute("""
                UPDATE accounts SET is_enabled = false, updated_at = %s
                WHERE account_type = 'country' AND is_dynamic = true
                    AND country_code != ALL(%s)
            """, (now, list(active_countries.keys())))
        else:
            cur.execute("""
                UPDATE accounts SET is_enabled = false, updated_at = %s
                WHERE account_type = 'country' AND is_dynamic = true
            """, (now,))

        conn.commit()

    log.info('reconcile complete active_countries=%d', len(active_countries))
