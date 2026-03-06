"""Rating system 0-600 points for proxy quality scoring."""


def ms_to_points(avg_ms: float | None) -> int:
    """0-20ms=100, 21-40=90, 41-60=80, ... every +20ms = -10pts, min 0."""
    if avg_ms is None:
        return 0
    if avg_ms <= 0:
        return 100
    bracket = int((avg_ms - 1) // 20)  # 0=0-20, 1=21-40, 2=41-60...
    return max(0, 100 - bracket * 10)


def success_rate_to_points(ok: int, error: int) -> int:
    """100% ok=100, 90%=90, 80%=80, ..., 0%=0."""
    total = ok + error
    if total == 0:
        return 0
    rate = ok / total
    return max(0, min(100, int(rate * 10) * 10))


def speed_to_points(mbps: float | None) -> int:
    """>=100Mbps=100, 90-99=90, 80-89=80, ..., 0-9=0."""
    if mbps is None or mbps <= 0:
        return 0
    if mbps >= 100:
        return 100
    return int(mbps // 10) * 10


def compute_rating(
    ping_avg_ms: float | None,
    ping_ok: int,
    ping_error: int,
    auth_avg_ms: float | None,
    auth_ok: int,
    auth_error: int,
    speedtest_download_mbps: float | None,
    speedtest_upload_mbps: float | None,
) -> int:
    """Compute total 0-600 rating from 6 metrics, each 0-100."""
    return (
        ms_to_points(ping_avg_ms)
        + success_rate_to_points(ping_ok, ping_error)
        + ms_to_points(auth_avg_ms)
        + success_rate_to_points(auth_ok, auth_error)
        + speed_to_points(speedtest_download_mbps)
        + speed_to_points(speedtest_upload_mbps)
    )
