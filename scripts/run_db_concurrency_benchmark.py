from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "loadtests" / "results"
DEFAULT_POSTGRES_URL = "postgresql://postgres:N0th1ing@127.0.0.1:5432/postgres"


@dataclass(frozen=True)
class RunSpec:
    name: str
    users: int
    duration_s: int


@dataclass(frozen=True)
class SuiteSpec:
    mode_name: str
    database_url: str
    port: int
    seed_scale: str
    runtime_cache_backend: str
    runtime_cache_url: str | None = None
    runtime_cache_namespace: str = "promptman"
    runtime_cache_disable_internal: str = "false"


@dataclass
class RunResult:
    db_mode: str
    run_name: str
    users: int
    duration_s: int
    total_requests: int
    successes: int
    failures: int
    failure_rate_pct: float
    rps: float
    avg_ms: float
    p95_ms: float
    p99_ms: float


@dataclass
class WorkerStats:
    latencies_ms: list[float]
    successes: int
    failures: int


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round((percentile / 100.0) * (len(ordered) - 1))))
    return round(ordered[rank], 2)


def _wait_http_ready(base_url: str, timeout_s: int = 60) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    with requests.Session() as session:
        session.trust_env = False
        while time.monotonic() < deadline:
            try:
                response = session.get(f"{base_url}/v1/version", timeout=2)
                if response.ok:
                    return
            except Exception as exc:  # pragma: no cover
                last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Server did not become ready in {timeout_s}s. Last error: {last_error}")


def _start_server(database_url: str, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env.setdefault("PROMPTMAN_KEY", "benchmark-local-key")

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)


def _seed_for_database(database_url: str, scale: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env.setdefault("PROMPTMAN_KEY", "benchmark-local-key")
    subprocess.run(
        [sys.executable, "scripts/seed_demo_data.py", "--scale", scale],
        cwd=str(PROJECT_ROOT),
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _authenticate(base_url: str) -> str:
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(
            f"{base_url}/v1/auth/login",
            json={"username": "demo_admin", "password": "demo_admin_2026"},
            timeout=10,
        )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("No access token returned by /v1/auth/login")
    return str(token)


def _thread_ids(base_url: str, token: str) -> list[int]:
    headers = {"Authorization": f"Bearer {token}"}
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(f"{base_url}/v1/conversations/threads?limit=500", headers=headers, timeout=10)
    response.raise_for_status()
    rows = response.json()
    return [int(item["id"]) for item in rows if isinstance(item, dict) and "id" in item]


def _apply_runtime_cache_config(
    base_url: str,
    token: str,
    *,
    backend: str,
    url: str | None,
    namespace: str,
    disable_internal: str,
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    updates = {
        "PROMPTMAN_RUNTIME_CACHE_BACKEND": backend,
        "PROMPTMAN_RUNTIME_CACHE_NAMESPACE": namespace,
        "PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL": disable_internal,
    }
    if url is not None:
        updates["PROMPTMAN_RUNTIME_CACHE_URL"] = url

    with requests.Session() as session:
        session.trust_env = False
        for key, value in updates.items():
            response = session.put(
                f"{base_url}/v1/admin/config/{key}",
                params={"value": value},
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()


def _worker(
    worker_id: int,
    base_url: str,
    token: str,
    stop_event: threading.Event,
    thread_ids: list[int],
) -> WorkerStats:
    rng = random.Random(worker_id * 7919 + int(time.time()))
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    latencies_ms: list[float] = []
    successes = 0
    failures = 0

    with requests.Session() as session:
        session.trust_env = False
        while not stop_event.is_set():
            op = rng.choices(
                population=["list_threads", "get_messages", "append_message", "analyze"],
                weights=[34, 31, 20, 15],
                k=1,
            )[0]
            thread_id = rng.choice(thread_ids)

            method = "GET"
            path = "/v1/conversations/threads?limit=50"
            payload: dict[str, Any] | None = None

            if op == "get_messages":
                path = f"/v1/conversations/threads/{thread_id}/messages"
            elif op == "append_message":
                method = "POST"
                path = f"/v1/conversations/threads/{thread_id}/messages"
                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"benchmark-worker-{worker_id} tick={time.time_ns()}",
                        }
                    ]
                }
            elif op == "analyze":
                method = "POST"
                path = f"/v1/conversations/analyze/{thread_id}"

            started = time.perf_counter()
            try:
                response = session.request(
                    method,
                    f"{base_url}{path}",
                    headers=headers,
                    json=payload,
                    timeout=10,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                latencies_ms.append(elapsed_ms)
                if 200 <= response.status_code < 300:
                    successes += 1
                else:
                    failures += 1
            except Exception:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                latencies_ms.append(elapsed_ms)
                failures += 1

    return WorkerStats(latencies_ms=latencies_ms, successes=successes, failures=failures)


def _run_workload(base_url: str, token: str, users: int, duration_s: int, thread_ids: list[int]) -> RunResult:
    if not thread_ids:
        raise RuntimeError("No threads available for workload. Seed failed or returned empty dataset.")

    stop_event = threading.Event()
    started_at = time.perf_counter()

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(_worker, i + 1, base_url, token, stop_event, thread_ids) for i in range(users)]
        time.sleep(duration_s)
        stop_event.set()
        stats = [future.result() for future in futures]

    elapsed_s = max(0.001, time.perf_counter() - started_at)
    all_latencies = [lat for stat in stats for lat in stat.latencies_ms]
    successes = sum(stat.successes for stat in stats)
    failures = sum(stat.failures for stat in stats)
    total = successes + failures

    return RunResult(
        db_mode="",
        run_name="",
        users=users,
        duration_s=duration_s,
        total_requests=total,
        successes=successes,
        failures=failures,
        failure_rate_pct=round((failures / total) * 100.0, 2) if total else 0.0,
        rps=round(total / elapsed_s, 2),
        avg_ms=round(statistics.fmean(all_latencies), 2) if all_latencies else 0.0,
        p95_ms=_percentile(all_latencies, 95),
        p99_ms=_percentile(all_latencies, 99),
    )


def _run_suite(suite: SuiteSpec, specs: list[RunSpec]) -> tuple[list[RunResult], str | None]:
    print(f"[{suite.mode_name}] seed start scale={suite.seed_scale}", flush=True)
    try:
        _seed_for_database(suite.database_url, suite.seed_scale)
    except Exception as exc:
        return [], f"seed failed: {exc}"
    print(f"[{suite.mode_name}] seed done", flush=True)

    server = _start_server(suite.database_url, suite.port)
    try:
        print(f"[{suite.mode_name}] waiting server on :{suite.port}", flush=True)
        base_url = f"http://127.0.0.1:{suite.port}"
        _wait_http_ready(base_url, timeout_s=90)
        token = _authenticate(base_url)
        print(f"[{suite.mode_name}] auth done", flush=True)
        _apply_runtime_cache_config(
            base_url,
            token,
            backend=suite.runtime_cache_backend,
            url=suite.runtime_cache_url,
            namespace=suite.runtime_cache_namespace,
            disable_internal=suite.runtime_cache_disable_internal,
        )
        print(f"[{suite.mode_name}] cache backend={suite.runtime_cache_backend} configured", flush=True)
        thread_ids = _thread_ids(base_url, token)

        rows: list[RunResult] = []
        for spec in specs:
            print(f"[{suite.mode_name}] run {spec.name} users={spec.users} duration={spec.duration_s}s", flush=True)
            result = _run_workload(
                base_url=base_url,
                token=token,
                users=spec.users,
                duration_s=spec.duration_s,
                thread_ids=thread_ids,
            )
            result.db_mode = suite.mode_name
            result.run_name = spec.name
            rows.append(result)
            print(
                f"[{suite.mode_name}] done {spec.name}: rps={result.rps} p95={result.p95_ms}ms fail={result.failure_rate_pct}%",
                flush=True,
            )
        return rows, None
    except Exception as exc:  # pragma: no cover
        return [], str(exc)
    finally:
        _stop_server(server)


def _write_report(results: list[RunResult], errors: dict[str, str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "results": [row.__dict__ for row in results],
        "errors": errors,
    }
    (output_dir / "db_concurrency_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# DB Concurrency Benchmark",
        "",
        f"Generated at (UTC): {payload['generated_at']}",
        "",
        "| DB | Run | Users | Duration(s) | Total req | RPS | Avg ms | P95 ms | P99 ms | Fail % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in results:
        lines.append(
            f"| {row.db_mode} | {row.run_name} | {row.users} | {row.duration_s} | {row.total_requests} | {row.rps} | {row.avg_ms} | {row.p95_ms} | {row.p99_ms} | {row.failure_rate_pct} |"
        )

    if errors:
        lines.append("")
        lines.append("## Errors")
        for key, value in errors.items():
            lines.append(f"- {key}: {value}")

    (output_dir / "db_concurrency_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_ROOT / "cache_compare" / f"concurrency_{timestamp}"

    postgres_url = os.getenv("BENCHMARK_POSTGRES_URL", DEFAULT_POSTGRES_URL)
    redis_url = os.getenv("BENCHMARK_REDIS_URL", "redis://127.0.0.1:6379/0")

    specs = [
        RunSpec(name="load_low", users=16, duration_s=12),
        RunSpec(name="load_high", users=48, duration_s=12),
        RunSpec(name="stress", users=96, duration_s=16),
    ]

    results: list[RunResult] = []
    errors: dict[str, str] = {}

    suites = [
        SuiteSpec(
            mode_name="postgres_memory",
            database_url=postgres_url,
            port=8012,
            seed_scale="large",
            runtime_cache_backend="memory",
            runtime_cache_url=redis_url,
        ),
        SuiteSpec(
            mode_name="postgres_redis",
            database_url=postgres_url,
            port=8013,
            seed_scale="large",
            runtime_cache_backend="redis",
            runtime_cache_url=redis_url,
        ),
    ]

    for suite in suites:
        rows, error = _run_suite(suite, specs)
        if error:
            errors[suite.mode_name] = error
        results.extend(rows)

    _write_report(results, errors, output_dir)

    print(f"Report directory: {output_dir}")
    print(f"Results rows: {len(results)}")
    if errors:
        print("Errors:")
        for key, value in errors.items():
            print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
