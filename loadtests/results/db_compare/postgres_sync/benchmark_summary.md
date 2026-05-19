# Benchmark Summary

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 33.40 | 67.00 | 40.87 | 0.00 | yes |
| mixed | 20 | 57.00 | 180.00 | 57.76 | 0.00 | yes |
| mixed | 40 | 60.62 | 690.00 | 264.26 | 0.00 | no |
| cache | 10 | 101.93 | 19.00 | 10.85 | 0.00 | yes |
| cache | 20 | 186.39 | 28.00 | 14.65 | 0.00 | yes |
| cache | 40 | 243.62 | 87.00 | 51.00 | 0.00 | yes |
| optimize_hot | 10 | 19.76 | 20.00 | 13.52 | 0.00 | yes |
| optimize_hot | 20 | 37.14 | 47.00 | 15.61 | 0.00 | yes |
| optimize_hot | 40 | 70.69 | 43.00 | 18.17 | 0.00 | yes |
| optimize_cold | 10 | 0.39 | 13000.00 | 7485.71 | 0.00 | no |
| optimize_cold | 20 | 0.00 | inf | inf | 100.00 | no |
| optimize_cold | 40 | 0.00 | inf | inf | 100.00 | no |
