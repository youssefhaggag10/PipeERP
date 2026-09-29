#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import http.cookiejar
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Result:
    duration_ms: float
    status: int
    path: str


def _request(opener: urllib.request.OpenerDirector, base_url: str, path: str) -> Result:
    started = time.monotonic()
    request = urllib.request.Request(f"{base_url}{path}", method="GET")
    try:
        with opener.open(request, timeout=15) as response:
            status = response.status
            response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
    except urllib.error.URLError:
        status = 0
    return Result((time.monotonic() - started) * 1000, status, path)


def _session(base_url: str, username: str, password: str) -> urllib.request.OpenerDirector:
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    body = json.dumps({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        f"{base_url}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener.open(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"login failed with {response.status}")
        response.read()
    return opener


def _worker(
    base_url: str,
    username: str,
    password: str,
    iterations: int,
    paths: tuple[str, ...],
) -> list[Result]:
    opener = _session(base_url, username, password)
    results: list[Result] = []
    for index in range(iterations):
        results.append(_request(opener, base_url, paths[index % len(paths)]))
    return results


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PipeERP authenticated five-session read load test"
    )
    parser.add_argument("--base-url", default=os.getenv("PIPEERP_BASE_URL", ""))
    parser.add_argument("--username", default=os.getenv("LOAD_TEST_USERNAME", ""))
    parser.add_argument("--password-file", default=os.getenv("LOAD_TEST_PASSWORD_FILE", ""))
    parser.add_argument("--users", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--p95-ms", type=float, default=1500)
    args = parser.parse_args()

    if not args.base_url or not args.username or not args.password_file:
        parser.error("base URL, username, and password file are required")
    if not args.base_url.startswith("https://") and os.getenv("ALLOW_HTTP_LOAD_TEST") != "YES":
        parser.error("HTTPS is required unless ALLOW_HTTP_LOAD_TEST=YES")
    if not 1 <= args.users <= 20 or not 1 <= args.iterations <= 1000:
        parser.error("users or iterations are outside the safe acceptance range")

    password = Path(args.password_file).read_text(encoding="utf-8").strip()
    current_year = date.today().year
    paths = (
        "/api/v1/auth/me",
        "/api/v1/inventory/balances",
        "/api/v1/purchases/orders?limit=25",
        "/api/v1/sales/orders?limit=25",
        "/api/v1/accounts/summary",
        "/api/v1/reports/generate?report_key=inventory_valuation"
        f"&date_from={current_year}-01-01&date_to={current_year}-12-31",
    )
    started = time.monotonic()
    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as executor:
        futures = [
            executor.submit(
                _worker,
                args.base_url.rstrip("/"),
                args.username,
                password,
                args.iterations,
                paths,
            )
            for _ in range(args.users)
        ]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    durations = [item.duration_ms for item in results]
    failures = [item for item in results if item.status != 200]
    summary = {
        "users": args.users,
        "requests": len(results),
        "failures": len(failures),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "mean_ms": round(statistics.fmean(durations), 2),
        "p50_ms": round(_percentile(durations, 0.50), 2),
        "p95_ms": round(_percentile(durations, 0.95), 2),
        "max_ms": round(max(durations), 2),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if failures:
        print(
            json.dumps([item.__dict__ for item in failures[:10]], ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    return 0 if summary["p95_ms"] <= args.p95_ms else 2


if __name__ == "__main__":
    raise SystemExit(main())
