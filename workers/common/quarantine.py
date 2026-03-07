def should_quarantine(success_rate: float, avg_latency_ms: float | None, flap_score: float, latency_threshold_ms: float = 1500) -> bool:
    if success_rate < 0.4:
        return True
    if avg_latency_ms is not None and avg_latency_ms > latency_threshold_ms * 1.5:
        return True
    if flap_score > 0.7:
        return True
    return False
