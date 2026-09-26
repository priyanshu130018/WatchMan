"""Production-safe in-memory rolling telemetry and metrics engine.

Tracks:
- Request counts, rates, and distributions (2xx, 3xx, 4xx, 5xx)
- Request latency percentiles (p50, p95, p99, min, max, avg)
- Route-level latency breakdowns
- TMDB API requests, errors, and cache hits
- Recommendation pipeline execution counts, latency, and failures
- Zero sensitive data leakage (no JWTs, passwords, keys, or auth headers)
"""

import time
import math
import threading
from collections import deque
from typing import Any, Dict, List, Tuple


class TelemetryEngine:
    def __init__(self, max_samples: int = 2000):
        self._lock = threading.Lock()
        self.max_samples = max_samples
        
        # Overall request metrics
        self.total_requests: int = 0
        self.status_2xx: int = 0
        self.status_3xx: int = 0
        self.status_4xx: int = 0
        self.status_5xx: int = 0
        
        # Rolling request latency samples (in milliseconds)
        self.latency_samples: deque[float] = deque(maxlen=max_samples)
        
        # Route-level request counts and rolling latencies: {route: {"count": N, "latencies": deque}}
        self.route_metrics: Dict[str, Dict[str, Any]] = {}
        
        # External Dependency Telemetry: TMDB
        self.tmdb_requests: int = 0
        self.tmdb_cache_hits: int = 0
        self.tmdb_errors: int = 0
        self.tmdb_timeouts: int = 0
        self.tmdb_rate_limits: int = 0
        
        # Recommendation Pipeline Telemetry
        self.recommendation_runs: int = 0
        self.recommendation_failures: int = 0
        self.recommendation_latencies: deque[float] = deque(maxlen=500)
        self.recommendation_cold_starts: int = 0

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        """Record an incoming HTTP request with its status and duration."""
        normalized_route = self._normalize_path(path)
        route_key = f"{method.upper()} {normalized_route}"
        
        with self._lock:
            self.total_requests += 1
            if 200 <= status_code < 300:
                self.status_2xx += 1
            elif 300 <= status_code < 400:
                self.status_3xx += 1
            elif 400 <= status_code < 500:
                self.status_4xx += 1
            elif status_code >= 500:
                self.status_5xx += 1
            
            self.latency_samples.append(duration_ms)
            
            if route_key not in self.route_metrics:
                self.route_metrics[route_key] = {
                    "count": 0,
                    "errors_4xx": 0,
                    "errors_5xx": 0,
                    "latencies": deque(maxlen=200),
                }
            
            rm = self.route_metrics[route_key]
            rm["count"] += 1
            if 400 <= status_code < 500:
                rm["errors_4xx"] += 1
            elif status_code >= 500:
                rm["errors_5xx"] += 1
            rm["latencies"].append(duration_ms)

    def record_tmdb_call(self, cache_hit: bool = False, error_type: str | None = None):
        """Record TMDB API interaction telemetry."""
        with self._lock:
            self.tmdb_requests += 1
            if cache_hit:
                self.tmdb_cache_hits += 1
            if error_type:
                self.tmdb_errors += 1
                if error_type == "timeout":
                    self.tmdb_timeouts += 1
                elif error_type == "rate_limit":
                    self.tmdb_rate_limits += 1

    def record_recommendation_run(self, duration_ms: float, success: bool = True, is_cold_start: bool = False):
        """Record ML Recommendation pipeline execution."""
        with self._lock:
            self.recommendation_runs += 1
            if not success:
                self.recommendation_failures += 1
            if is_cold_start:
                self.recommendation_cold_starts += 1
            self.recommendation_latencies.append(duration_ms)

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Generate a production-safe snapshot of system request and latency metrics."""
        with self._lock:
            total = self.total_requests
            latencies = list(self.latency_samples)
            rec_latencies = list(self.recommendation_latencies)
            
            # Global percentiles
            p50, p95, p99, min_l, max_l, avg_l = self._calculate_percentiles(latencies)
            rec_p50, rec_p95, rec_p99, _, _, rec_avg = self._calculate_percentiles(rec_latencies)
            
            # Route breakdown
            route_stats = {}
            for r_key, r_data in sorted(self.route_metrics.items(), key=lambda x: x[1]["count"], reverse=True)[:15]:
                r_lats = list(r_data["latencies"])
                rp50, rp95, rp99, _, _, ravg = self._calculate_percentiles(r_lats)
                route_stats[r_key] = {
                    "count": r_data["count"],
                    "errors_4xx": r_data["errors_4xx"],
                    "errors_5xx": r_data["errors_5xx"],
                    "avg_ms": ravg,
                    "p50_ms": rp50,
                    "p95_ms": rp95,
                    "p99_ms": rp99,
                }
            
            return {
                "requests": {
                    "total": total,
                    "status_2xx": self.status_2xx,
                    "status_3xx": self.status_3xx,
                    "status_4xx": self.status_4xx,
                    "status_5xx": self.status_5xx,
                    "rate_2xx_pct": round((self.status_2xx / total * 100), 2) if total > 0 else 100.0,
                    "rate_4xx_pct": round((self.status_4xx / total * 100), 2) if total > 0 else 0.0,
                    "rate_5xx_pct": round((self.status_5xx / total * 100), 2) if total > 0 else 0.0,
                },
                "latency_ms": {
                    "sample_size": len(latencies),
                    "min": min_l,
                    "avg": avg_l,
                    "p50": p50,
                    "p95": p95,
                    "p99": p99,
                    "max": max_l,
                },
                "routes": route_stats,
                "dependencies": {
                    "tmdb": {
                        "total_requests": self.tmdb_requests,
                        "cache_hits": self.tmdb_cache_hits,
                        "cache_hit_rate_pct": round((self.tmdb_cache_hits / self.tmdb_requests * 100), 2) if self.tmdb_requests > 0 else 0.0,
                        "total_errors": self.tmdb_errors,
                        "timeouts": self.tmdb_timeouts,
                        "rate_limits": self.tmdb_rate_limits,
                    },
                },
                "ml_recommendation": {
                    "total_runs": self.recommendation_runs,
                    "failures": self.recommendation_failures,
                    "cold_starts": self.recommendation_cold_starts,
                    "avg_duration_ms": rec_avg,
                    "p50_ms": rec_p50,
                    "p95_ms": rec_p95,
                    "p99_ms": rec_p99,
                },
            }

    def _calculate_percentiles(self, samples: List[float]) -> Tuple[float, float, float, float, float, float]:
        """Compute p50, p95, p99, min, max, and avg from latency samples."""
        if not samples:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        
        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        
        def get_p(pct: float) -> float:
            k = (n - 1) * (pct / 100.0)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return round(sorted_samples[int(k)], 2)
            d0 = sorted_samples[int(f)] * (c - k)
            d1 = sorted_samples[int(c)] * (k - f)
            return round(d0 + d1, 2)
        
        p50 = get_p(50)
        p95 = get_p(95)
        p99 = get_p(99)
        min_v = round(sorted_samples[0], 2)
        max_v = round(sorted_samples[-1], 2)
        avg_v = round(sum(sorted_samples) / n, 2)
        
        return p50, p95, p99, min_v, max_v, avg_v

    def _normalize_path(self, path: str) -> str:
        """Group parameterized path segments (e.g. /api/movies/123 -> /api/movies/:id)."""
        parts = path.strip("/").split("/")
        norm_parts = []
        for p in parts:
            if p.isdigit() or (len(p) == 36 and "-" in p) or (len(p) == 32 and all(c in "0123456789abcdefABCDEF" for c in p)):
                norm_parts.append(":id")
            else:
                norm_parts.append(p)
        return "/" + "/".join(norm_parts)


# Singleton Telemetry Engine instance
telemetry = TelemetryEngine()
