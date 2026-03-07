import time
from datetime import datetime, timezone

from workers.common.db import get_conn
from workers.common.logging import get_logger
from workers.common.runtime import set_worker_state

log = get_logger('reconcile')


def main():
    set_worker_state('account_reconciler', 'running')
    while True:
        now = datetime.now(timezone.utc)
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("select country_code, count(*) as c from proxies where status='online' and is_enabled=true and is_quarantined=false and country_code is not null group by country_code")
            rows = {r['country_code'].lower(): r['c'] for r in cur.fetchall()}
            for cc, count in rows.items():
                if count >= 2:
                    cur.execute(
                        """insert into accounts(username, password, account_type, country_code, is_enabled, is_dynamic, min_required_working_proxies, created_at, updated_at, last_reconciled_at)
                           values (%s,%s,'country',%s,true,true,2,%s,%s,%s)
                           on conflict (username) do update set is_enabled=true, country_code=excluded.country_code, last_reconciled_at=excluded.last_reconciled_at, updated_at=excluded.updated_at""",
                        (cc, cc, cc, now, now, now),
                    )
            cur.execute("update accounts set is_enabled=false, last_reconciled_at=%s where account_type='country' and (country_code is null or country_code not in (select country_code from proxies where status='online' and is_enabled=true and is_quarantined=false and country_code is not null group by country_code having count(*) >= 2))", (now,))
            conn.commit()
        log.info('country accounts reconcile pass complete')
        time.sleep(120)


if __name__ == '__main__':
    main()
