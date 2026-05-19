# Benchmark Summary

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 34.28 | 140.00 | 27.07 | 0.00 | yes |
| mixed | 20 | 43.01 | 860.00 | 151.87 | 0.00 | no |
| mixed | 40 | 42.82 | 810.00 | 155.43 | 0.00 | no |
| cache | 10 | 102.26 | 19.00 | 9.18 | 0.00 | yes |
| cache | 20 | 189.02 | 30.00 | 13.68 | 0.00 | yes |
| cache | 40 | 255.70 | 80.00 | 45.51 | 0.00 | yes |
| optimize_hot | 10 | 19.50 | 19.00 | 9.41 | 0.00 | yes |
| optimize_hot | 20 | 38.48 | 35.00 | 11.60 | 0.00 | yes |
| optimize_hot | 40 | 72.01 | 39.00 | 13.85 | 0.00 | yes |
| optimize_cold | 10 | 0.16 | 12000.00 | 9396.95 | 0.00 | no |
| optimize_cold | 20 | 0.00 | inf | inf | 100.00 | no |
| optimize_cold | 40 | 0.00 | inf | inf | 100.00 | no |
