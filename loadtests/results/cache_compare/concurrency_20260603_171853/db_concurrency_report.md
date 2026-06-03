# DB Concurrency Benchmark

Generated at (UTC): 2026-06-03T14:20:33.120697+00:00

| DB | Run | Users | Duration(s) | Total req | RPS | Avg ms | P95 ms | P99 ms | Fail % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| postgres_memory | load_low | 16 | 12 | 2068 | 171.4 | 93.1 | 130.87 | 137.96 | 0.0 |
| postgres_memory | load_high | 48 | 12 | 2025 | 165.88 | 287.26 | 386.56 | 414.54 | 0.0 |
| postgres_memory | stress | 96 | 16 | 385 | 17.9 | 5275.88 | 10014.31 | 10014.47 | 49.87 |
| postgres_redis | load_low | 16 | 12 | 2087 | 173.07 | 92.26 | 130.18 | 139.28 | 0.0 |
| postgres_redis | load_high | 48 | 12 | 2017 | 164.99 | 288.7 | 383.78 | 417.32 | 0.0 |
| postgres_redis | stress | 96 | 16 | 629 | 27.3 | 3461.98 | 10013.92 | 10014.42 | 30.52 |
