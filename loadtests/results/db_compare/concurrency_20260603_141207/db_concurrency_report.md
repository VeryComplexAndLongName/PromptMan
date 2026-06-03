# DB Concurrency Benchmark

Generated at (UTC): 2026-06-03T11:13:47.102447+00:00

| DB | Run | Users | Duration(s) | Total req | RPS | Avg ms | P95 ms | P99 ms | Fail % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| postgres | load_low | 16 | 12 | 2007 | 166.32 | 95.94 | 138.54 | 170.55 | 0.0 |
| postgres | load_high | 48 | 12 | 2039 | 167.03 | 285.29 | 382.45 | 403.01 | 0.05 |
| postgres | stress | 96 | 16 | 825 | 34.18 | 2768.76 | 10010.01 | 10014.46 | 23.27 |

## Errors
- sqlite: HTTPConnectionPool(host='127.0.0.1', port=8011): Read timed out. (read timeout=10)
