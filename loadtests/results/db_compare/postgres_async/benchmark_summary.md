# Benchmark Summary

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 31.77 | 130.00 | 53.74 | 0.00 | yes |
| mixed | 20 | 41.76 | 700.00 | 169.63 | 0.00 | no |
| mixed | 40 | 36.22 | 3100.00 | 573.14 | 0.00 | no |
| cache | 10 | 98.69 | 22.00 | 12.70 | 0.00 | yes |
| cache | 20 | 173.16 | 40.00 | 21.02 | 0.00 | yes |
| cache | 40 | 179.72 | 200.00 | 99.25 | 0.00 | yes |
| optimize_hot | 10 | 19.19 | 23.00 | 17.58 | 0.00 | yes |
| optimize_hot | 20 | 36.99 | 33.00 | 19.52 | 0.00 | yes |
| optimize_hot | 40 | 68.62 | 100.00 | 30.02 | 0.00 | yes |
| optimize_cold | 10 | 0.18 | 11000.00 | 7144.59 | 0.00 | no |
| optimize_cold | 20 | 0.00 | inf | inf | 100.00 | no |
| optimize_cold | 40 | 0.00 | inf | inf | 100.00 | no |
