import time
from datetime import datetime, timezone

import maxminddb

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.common.runtime import set_worker_state

log = get_logger('geo')

MMDB_PATH = '/app/workers/GeoLite2-Country.mmdb'


def resolve_country(reader, ip: str) -> str | None:
    try:
        result = reader.get(ip)
        if result and 'country' in result:
            return result['country']['iso_code'].lower()
    except Exception:
        pass
    return None


def main():
    set_worker_state('geo_resolver', 'running')
    reader = maxminddb.open_database(MMDB_PATH)
    while True:
        now = datetime.now(timezone.utc)
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select id, host(host) as host from proxies where country_manual_override=false and country_code is null order by coalesce(last_geo_attempt_at, first_seen_at) asc nulls first limit 200")
            rows = cur.fetchall()
            for row in rows:
                country = resolve_country(reader, row['host'])
                cur.execute("insert into proxy_geo_attempts(proxy_id, success, detected_country_code, source, attempted_at) values (%s,%s,%s,'mmdb',%s)", (row['id'], bool(country), country, now))
                if country:
                    cur.execute("update proxies set country_code=%s, country_source='mmdb', last_geo_attempt_at=%s where id=%s", (country, now, row['id']))
                else:
                    cur.execute("update proxies set last_geo_attempt_at=%s where id=%s", (now, row['id']))
            conn.commit()
        log.info('geo resolution pass complete resolved=%d/%d', sum(1 for r in rows if resolve_country(reader, r['host'])), len(rows))
        time.sleep(60)


if __name__ == '__main__':
    main()
