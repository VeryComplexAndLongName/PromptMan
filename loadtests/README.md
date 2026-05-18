# Load Testing

This folder provides repeatable load testing for Prompt Man using Locust.

## What you get

- `locustfile.py`: authenticated Locust scenarios for `mixed`, `cache`, `optimize_hot`, and `optimize_cold` workloads.
- `benchmark_rps.py`: runs Locust headless across one or more scenarios and writes a manifest-backed summary.
- CSV artifacts per run in `loadtests/results/<scenario>/`.
- `results/benchmark_summary.md`: latest scenario table for README updates.

## Install

```powershell
pip install locust
```

or use project dev dependencies:

```powershell
uv sync --extra dev
```

## Run interactive Locust UI

```powershell
$env:LOADTEST_SCENARIO="mixed"
locust -f loadtests/locustfile.py -H http://127.0.0.1:8000
```

Then open: http://127.0.0.1:8089

Available scenarios:

- `mixed`
	- list/search/create/update plus low-rate optimize traffic
- `cache`
	- repeated hot reads (`GET /prompts`, detail, search, versions) plus repeated identical `POST /optimize`
	- intended to exercise the shared in-memory cache path
- `optimize_hot`
	- repeated identical `POST /optimize` requests with no prompt-read traffic mixed in
	- intended to measure the pure hot-cache optimization path against `optimize_cold`
- `optimize_cold`
	- repeated `POST /optimize` with unique payloads so cache keys never match
	- intended to quantify the cost of cache misses against the hot-cache scenario

## Run automated benchmark (RPS + p95 + failures)

```powershell
python loadtests/benchmark_rps.py --host http://127.0.0.1:8000 --duration 15s --users 10 20 40 --spawn-rate 10 --scenarios mixed cache optimize_hot optimize_cold --clean
```

The runner now:

- fetches one bearer token up front and reuses it for all Locust users
- writes scenario CSVs into `loadtests/results/mixed/`, `loadtests/results/cache/`, `loadtests/results/optimize_hot/`, and `loadtests/results/optimize_cold/`
- emits `benchmark_manifest.json` so charts only use fresh scenario runs
- emits `benchmark_summary.md` for quick documentation updates
- pairs naturally with the unit test `test_cached_optimization_is_faster_than_cold_optimization`

## Build charts from benchmark CSV

```powershell
python loadtests/generate_charts.py
```

Generated files:

- `loadtests/chart_rps.png`
- `loadtests/chart_p95_latency.png`
- `loadtests/chart_avg_latency.png`
- `loadtests/chart_failure_rate.png`
- `loadtests/chart_dashboard.png`
- `loadtests/chart_optimize_compare.png`

Current benchmark summary (`15s`, users `10/20/40`, local server, default thresholds):

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 24.17 | 1000.00 | 158.50 | 0.00 | no |
| mixed | 20 | 13.38 | 4600.00 | 1075.67 | 0.00 | no |
| mixed | 40 | 10.71 | 1000.00 | 104.25 | 0.00 | no |
| cache | 10 | 97.51 | 31.00 | 13.23 | 0.00 | yes |
| cache | 20 | 162.20 | 58.00 | 27.94 | 0.00 | yes |
| cache | 40 | 174.15 | 160.00 | 104.27 | 0.00 | yes |
| optimize_hot | 10 | 19.75 | 37.00 | 13.40 | 0.00 | yes |
| optimize_hot | 20 | 37.87 | 35.00 | 15.38 | 0.00 | yes |
| optimize_hot | 40 | 68.47 | 66.00 | 25.81 | 0.00 | yes |
| optimize_cold | 10 | 0.18 | 11000.00 | 6947.02 | 0.00 | no |
| optimize_cold | 20 | 0.00 | inf | inf | 100.00 | no |
| optimize_cold | 40 | 0.00 | inf | inf | 100.00 | no |

Cache impact takeaway:

- dedicated hot optimize traffic (`optimize_hot`) reached `19.75 RPS` at 10 users with `37 ms` p95 and stayed healthy through 40 users
- dedicated cold optimize traffic (`optimize_cold`) dropped to `0.18 RPS` with `11 s` p95 at 10 users and completed no optimize requests at 20 or 40 users in the 15-second window
- at 10 users, the hot optimize path delivered about `110x` higher throughput and about `297x` lower p95 latency than the cold optimize path
- the timing unit test in `tests/unit/test_unit_optimizer_and_crud.py` now asserts that repeated cache hits are materially faster than repeated cold requests

Default pass criteria:

- failure rate <= 1%
- p95 <= 500 ms

Override thresholds:

```powershell
python loadtests/benchmark_rps.py --max-failure-rate 0.02 --max-p95-ms 800
```

## Notes

- Run the server without auto-reload for cleaner numbers (`uvicorn main:app`).
- The cache scenario assumes the shared in-memory cache is enabled inside the app process under test.
- The optimize comparison chart is driven from `benchmark_manifest.json`, so it reflects scenario-aware `/optimize` metrics rather than aggregated setup traffic.
- The scenario comparison is most meaningful when both scenarios target the same server process and database state.
