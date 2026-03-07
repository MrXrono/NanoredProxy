from app.config import TRAFFIC_FLUSH_BYTES
from app.auth import update_traffic


class TrafficMeter:
    def __init__(self):
        self.counters = {}

    def add_local(self, conn_id, bytes_in, bytes_out):
        cur = self.counters.setdefault(conn_id, {'bytes_in': 0, 'bytes_out': 0, 'pending_in': 0, 'pending_out': 0})
        cur['bytes_in'] += bytes_in
        cur['bytes_out'] += bytes_out
        cur['pending_in'] += bytes_in
        cur['pending_out'] += bytes_out
        return cur

    async def maybe_flush(self, session_id: str, conn_id: str):
        cur = self.counters.get(conn_id)
        if not cur:
            return
        if cur['pending_in'] + cur['pending_out'] >= TRAFFIC_FLUSH_BYTES:
            await update_traffic(session_id, conn_id, cur['pending_in'], cur['pending_out'])
            cur['pending_in'] = 0
            cur['pending_out'] = 0

    async def flush_all(self, session_id: str, conn_id: str):
        cur = self.counters.get(conn_id)
        if not cur:
            return 0, 0
        if cur['pending_in'] or cur['pending_out']:
            await update_traffic(session_id, conn_id, cur['pending_in'], cur['pending_out'])
            cur['pending_in'] = 0
            cur['pending_out'] = 0
        return cur['bytes_in'], cur['bytes_out']

    def clear(self, conn_id: str):
        self.counters.pop(conn_id, None)


traffic_meter = TrafficMeter()
