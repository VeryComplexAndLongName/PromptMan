## Prompt Efficiency Analyzer

PromptMan includes a local deterministic Prompt Efficiency Analyzer for prompt-version quality diagnostics.
The analyzer does not call LLMs and does not require heavyweight ML dependencies.

Code is the source of truth:

- `prompt_efficiency_analizer/analyzer.py`
- `prompt_efficiency_analizer/quality_metrics.py`
- `prompt_efficiency_analizer/similarity.py`
- `prompt_efficiency_analizer/cache_estimator.py`
- `prompt_efficiency_analizer/drift.py`
- `prompt_efficiency_analizer/report.py`

---

## What It Analyzes

For a sequence of versions (`v1 -> v2 -> v3 -> ...`), the analyzer computes:

1. Similarity between adjacent versions.
2. Cache hit estimate between adjacent versions.
3. Context drift between adjacent versions.
4. Segment-level volatility between adjacent versions.
5. Placeholder stability (added/removed variables) between adjacent versions.
6. Prompt-level quality metrics per version.
7. Aggregated summary metrics across the whole chain.

---

## Input Segments

Prompts are normalized into canonical segments:

- `role`
- `task`
- `constraints`
- `output_format`
- `examples`
- `context`

---

## Core Formulas (Actual Implementation)

### Similarity

The analyzer uses three lexical similarities and one weighted hybrid:

- `levenshtein = Levenshtein.normalized_similarity(left, right)`
- `jaro_winkler = JaroWinkler.normalized_similarity(left, right)`
- `jaccard = Jaccard(token_set(left), token_set(right))`
- `hybrid = 0.45 * levenshtein + 0.35 * jaro_winkler + 0.20 * jaccard`

### Cache Hit Score

Cache estimate is weighted by segment stability (not token ratio):

1. For static segments (`role`, `task`, `constraints`, `output_format`, `examples`) compute average hybrid similarity `static_score`.
2. Compute context hybrid similarity `context_score`.
3. `weighted = 0.78 * static_score + 0.22 * context_score`.
4. If `context_score < 0.40`, apply penalty: `weighted = weighted * 0.85`.
5. Clamp result to `[0, 1]`.

### Context Drift

Context drift uses set symmetric difference on lowercase words:

- `drift = |words(prev) XOR words(curr)| / |words(prev) UNION words(curr)|`

### PSI (Prompt Stability Index)

PSI is computed from aggregated chain metrics:

- `mean_similarity = average(pairwise_hybrid)`
- `mean_cache = average(cache_hit_scores)`
- `drift_component = 1 - clamp(context_drift_mean, 0, 1)`
- `psi_raw = 0.45 * mean_similarity + 0.35 * mean_cache + 0.20 * drift_component`
- `psi = clamp(psi_raw, 0, 1) * 100`

---

## Additional Prompt-Level Metrics

Each prompt version now includes a `quality` block with:

1. `constraint_strictness`
Definition: density of strict directives (`must`, `must not`, `always`, `never`, `exactly`, etc.).

2. `ambiguity`
Definition: density of ambiguous wording (`maybe`, `perhaps`, `approximately`, `etc`, etc.).

3. `output_schema_compliance`
Definition: heuristic score from explicit schema/format keywords and structural cues (JSON-like keys, markdown headings, code fences, table pipes, enumerations).

4. `redundancy`
Definition: lexical repetition score from unique-token ratio and repeated bigrams.

5. `instruction_conflict_risk` and `instruction_conflicts`
Definition: conflict risk from contradictory phrase pairs (`must` vs `must not`, `always` vs `never`, etc.) and competing `exactly N` constraints.

6. `injection_surface_score` and `injection_matched_patterns`
Definition: heuristic detection of risky prompt-injection markers in context/examples.

7. `readability_difficulty`
Definition: parser/readability difficulty from sentence length, symbol density, and structural nesting signals.

8. `placeholder_count` and `placeholders`
Definition: extracted variable placeholders from patterns such as `{x}`, `{{x}}`, `<x>`, `$x`, `%%x%%`.

9. `token_budget`
Definition: context-window safety metrics:
`context_window_tokens`, `total_tokens`, `remaining_tokens`, `usage_ratio`, `safety_ratio`, `is_over_budget`.

Default context windows by encoding:

- `cl100k_base`: 128000
- `o200k_base`: 200000
- `p50k_base`: 8192
- `r50k_base`: 4096

---

## Additional Transition Metrics

Each transition (`vN -> vN+1`) includes:

1. `segment_volatility`
Per-segment change score:
`segment_volatility[segment] = 1 - hybrid_similarity(segment_prev, segment_curr)`.

2. `placeholder_stability`
Stability of placeholder set between versions.

3. `placeholder_added` / `placeholder_removed`
Which placeholders were introduced/removed.

4. `token_delta`
`current_total_tokens - previous_total_tokens`.

---

## Summary Fields

`summary` now includes base metrics plus aggregated quality metrics:

- `source`
- `prompt_count`
- `psi`
- `avg_cache_hit_score`
- `avg_hybrid_similarity`
- `context_drift_mean`
- `context_drift_max`
- `encoding`
- `avg_constraint_strictness`
- `avg_ambiguity`
- `avg_output_schema_compliance`
- `avg_redundancy`
- `avg_readability_difficulty`
- `max_instruction_conflict_risk`
- `max_injection_surface_score`
- `avg_placeholder_count`
- `min_token_budget_safety_ratio`
- `context_window_tokens`
- `avg_placeholder_stability`
- `avg_segment_volatility`

---

## Reports

The analyzer returns both:

1. `markdown_report`
2. `rich_report`

Reports include extended summary metrics and transition details.

---

## Dependencies

Current lightweight dependency set:

- `tiktoken`
- `rapidfuzz`
- `requests`
- `rich`

No `torch`, `transformers`, `spacy`, or other heavyweight ML stacks are required.

---

## Quick Usage

```python
from prompt_efficiency_analizer import PromptEfficiencyAnalyzer

analyzer = PromptEfficiencyAnalyzer(encoding_name="cl100k_base")
result = analyzer.analyze_prompt_chain(
    [
        {
            "label": "v1",
            "role": "assistant",
            "task": "Summarize ticket {ticket_id}",
            "constraints": "Must use exactly 3 bullets",
            "output_format": "JSON with keys: summary, actions",
            "context": "Support issue details",
            "examples": "Input: ... Output: ...",
        },
        {
            "label": "v2",
            "role": "assistant",
            "task": "Summarize ticket {ticket_id} and provide action plan",
            "constraints": "Must use exactly 3 bullets",
            "output_format": "JSON with keys: summary, actions, risk",
            "context": "Support issue details with escalation notes",
            "examples": "Input: ... Output: ...",
        },
    ]
)

print(result["summary"])
print(result["markdown_report"])
```

---

## Notes

1. Metric values are heuristic and intended for prompt quality monitoring, regression detection, and CI quality gates.
2. Because the analysis is deterministic and local, results are stable and reproducible for the same input.
