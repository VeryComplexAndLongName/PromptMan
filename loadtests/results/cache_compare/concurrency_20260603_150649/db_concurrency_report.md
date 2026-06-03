# DB Concurrency Benchmark

Generated at (UTC): 2026-06-03T12:08:18.688143+00:00

| DB | Run | Users | Duration(s) | Total req | RPS | Avg ms | P95 ms | P99 ms | Fail % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| postgres_memory | load_low | 16 | 12 | 1600 | 132.29 | 120.49 | 163.77 | 173.18 | 0.0 |
| postgres_memory | load_high | 48 | 12 | 1600 | 130.59 | 364.52 | 478.29 | 546.77 | 0.06 |
| postgres_memory | stress | 96 | 16 | 1999 | 120.81 | 783.24 | 1051.26 | 1339.85 | 0.05 |
| postgres_garnet | load_low | 16 | 12 | 1587 | 131.41 | 121.48 | 164.95 | 174.57 | 0.0 |
| postgres_garnet | load_high | 48 | 12 | 1576 | 128.25 | 370.69 | 488.12 | 541.08 | 0.06 |
| postgres_garnet | stress | 96 | 16 | 2037 | 122.92 | 769.0 | 1014.93 | 1279.66 | 0.0 |
