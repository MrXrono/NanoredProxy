def should_quarantine(success_rate: float, avg_latency_ms: float, flap_score: float, latency_threshold_ms: float = 1500) -> bool:
    return success_rate < 0.4 or avg_latency_ms > latency_threshold_ms * 1.5 or flap_score > 0.7
