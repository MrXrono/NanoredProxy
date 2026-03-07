class TrafficMeter:
    def __init__(self):
        self.counters = {}

    def add(self, conn_id, bytes_in, bytes_out):
        cur = self.counters.setdefault(conn_id, {"bytes_in": 0, "bytes_out": 0})
        cur["bytes_in"] += bytes_in
        cur["bytes_out"] += bytes_out

traffic_meter = TrafficMeter()
