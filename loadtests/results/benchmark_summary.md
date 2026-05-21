# Benchmark Summary

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 34.06 | 57.00 | 45.84 | 0.00 | yes |
| mixed | 20 | 62.84 | 130.00 | 32.91 | 0.00 | yes |
| mixed | 40 | 54.65 | 840.00 | 315.55 | 0.00 | no |
| cache | 10 | 102.62 | 21.00 | 9.64 | 0.00 | yes |
| cache | 20 | 165.32 | 67.00 | 27.55 | 0.00 | yes |
| cache | 40 | 140.46 | 260.00 | 148.98 | 0.00 | yes |
| optimize_hot | 10 | 19.34 | 23.00 | 11.99 | 0.00 | yes |
| optimize_hot | 20 | 38.28 | 23.00 | 12.26 | 0.00 | yes |
| optimize_hot | 40 | 68.79 | 72.00 | 23.99 | 0.00 | yes |
| optimize_cold | 10 | 0.18 | 11000.00 | 6985.02 | 0.00 | no |
| optimize_cold | 20 | 0.00 | inf | inf | 100.00 | no |
| optimize_cold | 40 | 0.00 | inf | inf | 100.00 | no |
