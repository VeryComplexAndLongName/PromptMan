# Load Testing (Archive)

The active load-test scripts for the legacy prompt/optimize API were removed during the conversation-first refactor.

This folder currently keeps historical benchmark artifacts (`*.png`, `results/`) for reference only.

## Current State

- No maintained Locust scenario file is shipped here.
- No maintained benchmark runner script is shipped here.
- Historical charts remain as archived evidence from previous API generations.

## If you need new benchmarks

Create a new harness targeting current conversation endpoints under `/v1/conversations`.
Recommended baseline scenarios:

1. Thread list/read hot path
2. Message append write path
3. Import JSON/Text path
4. Analyze path
5. Cache backend comparison (`memory` vs `redis`/`garnet`)
