# Benchmark Summary

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 9.91 | 3800.00 | 553.33 | 0.00 | no |
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
