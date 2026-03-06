"""Geo Agent: resolve country codes using local GeoLite2 MMDB."""

from datetime import datetime, timezone

import maxminddb

from workers.common.db import get_conn
from workers.common.logging import get_logger

log = get_logger('geo_agent')
MMDB_PATH = '/app/workers/GeoLite2-Country.mmdb'
_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        _reader = maxminddb.open_database(MMDB_PATH)
    return _reader


def run_geo_cycle():
    """Single pass: resolve up to 200 proxies without country_code."""
    reader = _get_reader()
    now = datetime.now(timezone.utc)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, host(host) AS host FROM proxies
            WHERE country_manual_override = false AND country_code IS NULL
            ORDER BY coalesce(last_geo_attempt_at, first_seen_at) ASC NULLS FIRST
            LIMIT 200
        """)
        rows = cur.fetchall()

        resolved = 0
        for row in rows:
            country = None
            try:
                result = reader.get(row['host'])
                if result and 'country' in result:
                    country = result['country']['iso_code'].lower()
            except Exception:
                pass

            cur.execute("""
                INSERT INTO proxy_geo_attempts(proxy_id, success, detected_country_code,
                    source, attempted_at)
                VALUES (%s, %s, %s, 'mmdb', %s)
            """, (row['id'], bool(country), country, now))

            if country:
                cur.execute("""
                    UPDATE proxies SET country_code = %s, country_source = 'mmdb',
                        last_geo_attempt_at = %s WHERE id = %s
                """, (country, now, row['id']))
                resolved += 1
            else:
                cur.execute("""
                    UPDATE proxies SET last_geo_attempt_at = %s WHERE id = %s
                """, (now, row['id']))

        conn.commit()

    log.info('geo cycle complete resolved=%d/%d', resolved, len(rows))
    return len(rows)  # return count for queue to know if more work needed
