from datetime import datetime, timezone

from workers.common.db import get_conn


def get_setting(key: str, default=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute('select value from system_settings where key=%s', (key,))
        row = cur.fetchone()
        return (row or {}).get('value', default)


def set_worker_state(worker_name: str, status: str, pause_reason: str | None = None):
    with get_conn() as conn, conn.cursor() as cur:
        now = datetime.now(timezone.utc)
        cur.execute(
            """update scheduler_state set status=%s, pause_reason=%s, updated_at=%s,
               last_started_at=case when %s='running' then %s else last_started_at end,
               last_finished_at=case when %s in ('idle','paused','error') then %s else last_finished_at end
               where worker_name=%s""",
            (status, pause_reason, now, status, now, status, now, worker_name),
        )
        conn.commit()


def active_sessions_count() -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("select count(*) as c from sessions where status='active'")
        return int(cur.fetchone()['c'])
