import json
import time
import urllib.request
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.common.runtime import set_worker_state

log = get_logger('geo')


def resolve_country(ip: str) -> str | None:
    try:
        with urllib.request.urlopen(f'https://ipapi.co/{ip}/json/', timeout=10) as resp:
            data = json.loads(resp.read().decode())
            code = data.get('country_code')
            return code.lower() if code else None
    except Exception:
        return None


def main():
    set_worker_state('geo_resolver', 'running')
    while True:
        now = datetime.now(timezone.utc)
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select id, host(host) as host from proxies where country_manual_override=false and (country_code is null or status='country_unknown') order by coalesce(last_geo_attempt_at, first_seen_at) asc nulls first limit 50")
            rows = cur.fetchall()
            for row in rows:
                country = resolve_country(row['host'])
                cur.execute("insert into proxy_geo_attempts(proxy_id, success, detected_country_code, source, attempted_at) values (%s,%s,%s,'auto',%s)", (row['id'], bool(country), country, now))
                if country:
                    cur.execute("update proxies set country_code=%s, country_source='auto', last_geo_attempt_at=%s where id=%s", (country, now, row['id']))
                else:
                    cur.execute("update proxies set status='country_unknown', last_geo_attempt_at=%s where id=%s", (now, row['id']))
            conn.commit()
        log.info('geo resolution pass complete')
        time.sleep(60)


if __name__ == '__main__':
    main()
