from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import requests


SCENARIO_TARGET_NAMES = {
    "optimize_hot": "POST /optimize [hot]",
    "optimize_cold": "POST /optimize [cold]",
}


@dataclass
class RunResult:
    scenario: str
    users: int
    requests_per_s: float
    failure_rate: float
    p95_ms: float
    avg_ms: float
    passed: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate sustainable RPS with Locust step runs.")
    parser.add_argument("--host", default="http://127.0.0.1:8000", help="Base URL for tested API")
    parser.add_argument("--duration", default="45s", help="Duration for each step run, e.g. 45s, 2m")
    parser.add_argument("--users", nargs="+", type=int, default=[10, 20, 40, 80], help="User levels")
    parser.add_argument("--spawn-rate", type=int, default=5, help="Locust spawn rate")
    parser.add_argument("--max-failure-rate", type=float, default=0.01, help="Pass threshold for failure ratio")
    parser.add_argument("--max-p95-ms", type=float, default=500.0, help="Pass threshold for p95 latency")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["mixed", "cache", "optimize_hot", "optimize_cold"],
        help="Scenario names passed through LOADTEST_SCENARIO",
    )
    parser.add_argument(
        "--locustfile",
        default="loadtests/locustfile.py",
        help="Path to locustfile",
    )
    parser.add_argument(
        "--outdir",
        default="loadtests/results",
        help="Directory where Locust CSV files are written",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove selected scenario result directories before writing fresh CSV files",
    )
    parser.add_argument("--username", default="admin", help="Benchmark login username")
    parser.add_argument("--password", default="admin", help="Benchmark login password")
    return parser.parse_args()


def _load_stats(stats_csv: Path, target_name: str | None = None) -> tuple[float, float, float, float] | None:
    with stats_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        aggregated_row: dict[str, str] | None = None
        for row in reader:
            row_name = row.get("Name")
            if target_name and row_name == target_name:
                req_count = float(row["Request Count"])
                fail_count = float(row["Failure Count"])
                rps = float(row["Requests/s"])
                p95_raw = row["95%"]
                avg_raw = row["Average Response Time"]
                if req_count <= 0 or p95_raw == "N/A" or avg_raw == "N/A":
                    return None
                p95 = float(p95_raw)
                avg = float(avg_raw)
                failure_rate = (fail_count / req_count) if req_count else 0.0
                return rps, failure_rate, p95, avg

            if row_name == "Aggregated":
                aggregated_row = row

        if aggregated_row is not None and target_name is None:
            req_count = float(aggregated_row["Request Count"])
            fail_count = float(aggregated_row["Failure Count"])
            rps = float(aggregated_row["Requests/s"])
            p95_raw = aggregated_row["95%"]
            avg_raw = aggregated_row["Average Response Time"]
            if req_count <= 0 or p95_raw == "N/A" or avg_raw == "N/A":
                return None
            p95 = float(p95_raw)
            avg = float(avg_raw)
            failure_rate = (fail_count / req_count) if req_count else 0.0
            return rps, failure_rate, p95, avg
    return None


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _fetch_auth_token(host: str, username: str, password: str) -> str:
    response = requests.post(
        f"{host.rstrip('/')}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Benchmark login did not return access_token")
    return token


def _run_scenario(args: argparse.Namespace, scenario: str, outdir: Path) -> list[RunResult]:
    scenario_dir = outdir / scenario
    if args.clean and scenario_dir.exists():
        shutil.rmtree(scenario_dir)
    scenario_dir.mkdir(parents=True, exist_ok=True)

    auth_token = _fetch_auth_token(args.host, args.username, args.password)

    results: list[RunResult] = []
    for users in args.users:
        prefix = scenario_dir / f"u{users}"
        cmd = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            args.locustfile,
            "--headless",
            "--host",
            args.host,
            "-u",
            str(users),
            "-r",
            str(args.spawn_rate),
            "-t",
            args.duration,
            "--only-summary",
            "--csv",
            str(prefix),
        ]

        env = dict(os.environ)
        env["LOADTEST_SCENARIO"] = scenario
        env["LOADTEST_AUTH_TOKEN"] = auth_token
        env["LOADTEST_USERNAME"] = args.username
        env["LOADTEST_PASSWORD"] = args.password

        print(f"\n== Running scenario={scenario}, users={users}, duration={args.duration} ==")
        completed = subprocess.run(cmd, check=False, env=env)
        if completed.returncode != 0:
            print(f"Locust run failed for scenario={scenario}, users={users} (exit={completed.returncode})")
            break

        stats_csv = Path(f"{prefix}_stats.csv")
        if not stats_csv.exists():
            print(f"Stats CSV missing for scenario={scenario}, users={users}: {stats_csv}")
            break

        parsed_stats = _load_stats(stats_csv, target_name=SCENARIO_TARGET_NAMES.get(scenario))
        if parsed_stats is None:
            print(f"No valid stats for scenario={scenario}, users={users}; marking as failed step.")
            results.append(
                RunResult(
                    scenario=scenario,
                    users=users,
                    requests_per_s=0.0,
                    failure_rate=1.0,
                    p95_ms=float("inf"),
                    avg_ms=float("inf"),
                    passed=False,
                )
            )
            continue

        rps, failure_rate, p95, avg = parsed_stats
        passed = failure_rate <= args.max_failure_rate and p95 <= args.max_p95_ms
        result = RunResult(
            scenario=scenario,
            users=users,
            requests_per_s=rps,
            failure_rate=failure_rate,
            p95_ms=p95,
            avg_ms=avg,
            passed=passed,
        )
        results.append(result)

        print(
            "scenario={scenario} users={users} rps={rps} failure_rate={failure_rate} p95={p95}ms avg={avg}ms pass={passed}".format(
                scenario=scenario,
                users=users,
                rps=_fmt(rps),
                failure_rate=_fmt(failure_rate * 100) + "%",
                p95=_fmt(p95),
                avg=_fmt(avg),
                passed=passed,
            )
        )

    return results


def _write_manifest(outdir: Path, scenarios: list[str], results: list[RunResult]) -> None:
    manifest = {
        "scenarios": scenarios,
        "results": [asdict(result) for result in results],
    }
    (outdir / "benchmark_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    summary_lines = [
        "# Benchmark Summary",
        "",
        "| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |",
        "| --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for result in results:
        summary_lines.append(
            "| {scenario} | {users} | {rps} | {p95} | {avg} | {fail} | {passed} |".format(
                scenario=result.scenario,
                users=result.users,
                rps=_fmt(result.requests_per_s),
                p95=_fmt(result.p95_ms),
                avg=_fmt(result.avg_ms),
                fail=_fmt(result.failure_rate * 100),
                passed="yes" if result.passed else "no",
            )
        )
    (outdir / "benchmark_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    scenario_results: list[RunResult] = []
    for scenario in args.scenarios:
        scenario_results.extend(_run_scenario(args, scenario, outdir))

    if not scenario_results:
        print("No successful runs were completed.")
        return 1

    _write_manifest(outdir, list(args.scenarios), scenario_results)

    finite_avg = [result.avg_ms for result in scenario_results if math.isfinite(result.avg_ms)]
    rms_latency = math.sqrt(sum(value * value for value in finite_avg) / len(finite_avg)) if finite_avg else float("inf")

    print("\n== Summary ==")
    for scenario in args.scenarios:
        scenario_subset = [result for result in scenario_results if result.scenario == scenario]
        if not scenario_subset:
            continue
        print(f"Scenario: {scenario}")
        for result in scenario_subset:
            status = "PASS" if result.passed else "FAIL"
            print(
                f"  {status} users={result.users} rps={_fmt(result.requests_per_s)} "
                f"p95={_fmt(result.p95_ms)}ms fail={_fmt(result.failure_rate * 100)}%"
            )

    print(f"RMS(avg_latency_ms) across runs: {_fmt(rms_latency)}")

    passed_results = [result for result in scenario_results if result.passed]
    if passed_results:
        best = max(passed_results, key=lambda item: item.requests_per_s)
        print(
            "Estimated sustainable throughput: "
            f"{_fmt(best.requests_per_s)} RPS at scenario={best.scenario}, users={best.users} "
            f"(p95={_fmt(best.p95_ms)}ms, fail={_fmt(best.failure_rate * 100)}%)"
        )
        return 0

    print("No run satisfied thresholds. Reduce load or loosen SLO thresholds.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
