"""
WatchMan Staging Concurrency & Performance Load Test Script.

Executes controlled concurrent requests across representative endpoints:
- GET /health
- GET /api/movies
- GET /api/web-series
- GET /api/search?q=Inception
- GET /api/recommendations

Measures throughput (req/sec), average latency, p50, p95, p99 latencies, and error rates.
"""

import sys
import time
import json
import statistics
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


def make_request(url: str, auth_token: str | None = None) -> tuple[str, int, float, bool]:
    start_time = time.time()
    req_headers = {"User-Agent": "WatchMan-ConcurrencyTest/1.0"}
    if auth_token:
        req_headers["Authorization"] = f"Bearer {auth_token}"

    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed = time.time() - start_time
            return url, resp.status, elapsed, True
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        # In staging without TMDB/recommendation data, 200 or 404 or empty list is expected
        return url, e.code, elapsed, e.code < 500
    except Exception as e:
        elapsed = time.time() - start_time
        return url, 0, elapsed, False


def run_concurrency_test(
    base_url: str = "http://localhost:3000",
    concurrency: int = 10,
    total_requests: int = 50,
    auth_token: str | None = None,
):
    print("=" * 70)
    print(f"Starting Controlled Concurrency Benchmark")
    print(f"Base URL:       {base_url}")
    print(f"Workers:        {concurrency}")
    print(f"Total Requests: {total_requests}")
    print("=" * 70)

    endpoints = [
        f"{base_url}/api/health",
        f"{base_url}/api/movies",
        f"{base_url}/api/web-series",
        f"{base_url}/api/search?q=Inception",
        f"{base_url}/api/recommendations",
    ]

    tasks = []
    for i in range(total_requests):
        url = endpoints[i % len(endpoints)]
        tasks.append((url, auth_token))

    latencies_by_endpoint: dict[str, list[float]] = {ep: [] for ep in endpoints}
    all_latencies: list[float] = []
    success_count = 0
    failure_count = 0
    status_counts: dict[int, int] = {}

    bench_start = time.time()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(make_request, url, token) for url, token in tasks]
        for future in as_completed(futures):
            url, status, elapsed, is_success = future.result()
            all_latencies.append(elapsed)
            latencies_by_endpoint[url].append(elapsed)
            status_counts[status] = status_counts.get(status, 0) + 1
            if is_success:
                success_count += 1
            else:
                failure_count += 1

    bench_elapsed = time.time() - bench_start
    throughput = len(tasks) / bench_elapsed if bench_elapsed > 0 else 0

    all_latencies.sort()
    avg_latency = statistics.mean(all_latencies) if all_latencies else 0
    p50_latency = statistics.median(all_latencies) if all_latencies else 0
    p95_idx = int(len(all_latencies) * 0.95)
    p99_idx = int(len(all_latencies) * 0.99)
    p95_latency = all_latencies[min(p95_idx, len(all_latencies) - 1)] if all_latencies else 0
    p99_latency = all_latencies[min(p99_idx, len(all_latencies) - 1)] if all_latencies else 0

    print("\n--- Benchmark Overall Results ---")
    print(f"Total Time Taken:    {bench_elapsed:.2f}s")
    print(f"Throughput:          {throughput:.2f} req/s")
    print(f"Successful Requests: {success_count}/{len(tasks)} ({(success_count/len(tasks))*100:.1f}%)")
    print(f"Failed Requests:     {failure_count}")
    print(f"Status Distribution: {status_counts}")
    print(f"Average Latency:     {avg_latency * 1000:.2f} ms")
    print(f"p50 Latency:         {p50_latency * 1000:.2f} ms")
    print(f"p95 Latency:         {p95_latency * 1000:.2f} ms")
    print(f"p99 Latency:         {p99_latency * 1000:.2f} ms")

    print("\n--- Latency Breakdown by Endpoint ---")
    for ep, lats in latencies_by_endpoint.items():
        if lats:
            lats.sort()
            ep_avg = statistics.mean(lats) * 1000
            ep_p95 = lats[min(int(len(lats) * 0.95), len(lats) - 1)] * 1000
            print(f"  {ep}")
            print(f"    Count: {len(lats)}, Avg: {ep_avg:.2f} ms, p95: {ep_p95:.2f} ms")

    print("=" * 70)
    return {
        "throughput": throughput,
        "avg_ms": avg_latency * 1000,
        "p50_ms": p50_latency * 1000,
        "p95_ms": p95_latency * 1000,
        "p99_ms": p99_latency * 1000,
        "success_rate": (success_count / len(tasks)) * 100,
        "total_requests": len(tasks),
        "status_distribution": status_counts,
    }


if __name__ == "__main__":
    token = sys.argv[1] if len(sys.argv) > 1 else None
    run_concurrency_test(auth_token=token)
