# DB Concurrency Benchmark

Generated at (UTC): 2026-06-03T12:13:39.934593+00:00

| DB | Run | Users | Duration(s) | Total req | RPS | Avg ms | P95 ms | P99 ms | Fail % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| postgres_memory | load_low | 16 | 12 | 1592 | 131.58 | 121.1 | 164.62 | 179.6 | 0.0 |
| postgres_memory | load_high | 48 | 12 | 1563 | 127.43 | 373.15 | 489.52 | 550.45 | 0.0 |
| postgres_memory | stress | 96 | 16 | 2066 | 125.2 | 756.35 | 996.12 | 1263.21 | 0.0 |
| postgres_redis | load_low | 16 | 12 | 1596 | 132.3 | 120.64 | 164.78 | 177.46 | 0.06 |
| postgres_redis | load_high | 48 | 12 | 1575 | 128.2 | 370.67 | 489.09 | 544.47 | 0.0 |
| postgres_redis | stress | 96 | 16 | 2023 | 122.1 | 774.51 | 1024.23 | 1339.09 | 0.0 |
