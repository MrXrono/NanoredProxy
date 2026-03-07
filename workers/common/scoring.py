def normalize_latency(latency_ms: float | None, threshold_ms: float = 1500.0) -> float:
    if latency_ms is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (latency_ms / max(threshold_ms, 1.0))))


def normalize_speed(download_mbps: float | None, upload_mbps: float | None, minimum: float = 10.0) -> float:
    if download_mbps is None and upload_mbps is None:
        return 0.0
    d = max(0.0, float(download_mbps or 0.0) / minimum)
    u = max(0.0, float(upload_mbps or 0.0) / minimum)
    return min(1.0, (d + u) / 2.0)


def composite_score(latency_score: float, speed_score: float, stability_score: float, real_traffic_score: float, failure_penalty: float = 0.0, quarantine_penalty: float = 0.0, sticky_bonus: float = 0.0, strategy: str = 'A') -> float:
    if strategy == 'B':
        value = latency_score * 0.45 + speed_score * 0.30 + stability_score * 0.20 + real_traffic_score * 0.05
    else:
        value = latency_score * 0.30 + speed_score * 0.20 + stability_score * 0.45 + real_traffic_score * 0.05
    return max(0.0, min(1.0, value + sticky_bonus - failure_penalty - quarantine_penalty))
