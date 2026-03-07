def composite_score(latency_score: float, speed_score: float, stability_score: float, real_traffic_score: float, failure_penalty: float = 0.0, quarantine_penalty: float = 0.0, sticky_bonus: float = 0.0) -> float:
    return max(0.0, latency_score * 0.3 + speed_score * 0.25 + stability_score * 0.3 + real_traffic_score * 0.15 + sticky_bonus - failure_penalty - quarantine_penalty)
