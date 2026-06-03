# DB Concurrency Benchmark

Generated at (UTC): 2026-06-03T14:18:09.380740+00:00

| DB | Run | Users | Duration(s) | Total req | RPS | Avg ms | P95 ms | P99 ms | Fail % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| postgres_memory | load_low | 16 | 12 | 2051 | 169.67 | 94.0 | 131.67 | 141.01 | 0.0 |
| postgres_memory | load_high | 48 | 12 | 2009 | 164.43 | 289.31 | 387.18 | 455.31 | 0.0 |
| postgres_memory | stress | 96 | 16 | 2589 | 157.3 | 602.84 | 811.67 | 996.75 | 0.0 |
| postgres_redis | load_low | 16 | 12 | 2100 | 174.05 | 91.72 | 129.57 | 137.6 | 0.0 |
| postgres_redis | load_high | 48 | 12 | 2015 | 164.63 | 289.63 | 386.39 | 432.77 | 0.05 |
| postgres_redis | stress | 96 | 16 | 1064 | 40.8 | 2108.57 | 10002.16 | 10014.23 | 15.79 |
