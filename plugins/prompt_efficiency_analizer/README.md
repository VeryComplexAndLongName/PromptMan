## Prompt Efficiency Analyzer

PromptMan includes a built‑in **Prompt Efficiency Analyzer** designed to measure the stability, predictability, and cache‑friendliness of prompt versions.  
The analyzer works **locally**, does not call any LLMs, and requires no external services.  
It evaluates prompt efficiency across several key metrics.

---

### Overview

The analyzer compares multiple versions of a prompt within the same `project/name` and computes:

- structural stability of the prompt  
- probability of hitting the LLM cache  
- degree of change in the dynamic context  
- textual and token‑level similarity between versions  
- transition quality between versions (v1 → v2 → v3 …)

The output includes aggregated metrics and a transition table.

---

### How it works (Diagram)

```
┌──────────────────────────┐
│  Prompt Versions (v1..vn)│
└──────────────┬───────────┘
               │
               ▼
┌────────────────────┐
│  Segmentation      │
│  (Role/Task/...)   │
└──────────┬─────────┘
           │
           ▼
┌──────────────────────────────┐
│ Token Counter (tiktoken)     │
└───────────┬──────────────────┘
            │
            ▼
┌────────────────────────────────────────┐
│ Similarity Engine (Jaro/Jaccard Hybrid)│
└──────────────────┬─────────────────────┘
                   │
                   ▼
┌───────────────────────────────────────┐
│ Cache Hit Estimator (static vs total) │
└──────────────────┬────────────────────┘
                   │
                   ▼
┌────────────────────────────┐
│ Context Drift Calculator   │
└──────────────┬─────────────┘
               │
               ▼
┌──────────────────────────┐
│  Final Efficiency Report │
└──────────────────────────┘
```

### Internal Algorythm Flowchart

```
┌───────────────────────────────┐
│   Input: Prompt Versions      │
│   (v1, v2, v3, ..., vn)       │
└───────────────┬───────────────┘
                │
                ▼
┌────────────────────────────────┐
│ 1. Segmentation                │
│    - Role                      │
│    - Task                      │
│    - Context                   │
│    - Constraints               │
│    - Output Format             │
└────────────────┬───────────────┘
                 │
                 ▼
┌────────────────────────────────┐
│ 2. Token Counting (tiktoken)   │
│    - static_tokens             │
│    - dynamic_tokens            │
│    - total_tokens              │
└────────────────┬───────────────┘
                 │
                 ▼
┌──────────────────────────────────────────┐
│ 3. Similarity Engine                     │
│    - Jaro-Winkler                        │
│    - Jaccard (token-level)               │
│    - Hybrid similarity                   │
└──────────────────────┬───────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────┐
│ 4. Cache Hit Estimator                   │
│    cache_hit = static_tokens / total     │
└──────────────────────┬───────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────┐
│ 5. Context Drift Calculator              │
│    drift = 1 - similarity(contexts)      │
└──────────────────────┬───────────────────┘
                       │
                       ▼
┌────────────────────────────────┐
│ 6. Aggregation & Reporting     │
│    - PSI                       │
│    - Avg Cache Hit Score       │
│    - Avg Hybrid Similarity     │
│    - Mean Context Drift        │
│    - Transition Table          │
└────────────────────────────────┘
```

---

## Metrics

Below are all metrics produced by the analyzer, including interpretation and recommended value ranges.

---

### **PSI — Prompt Stability Index**

**Definition:**  
Percentage of static tokens in the prompt (Role, Task, Constraints, Output Format) relative to the total number of tokens.

**Formula:**  
`PSI = (static_tokens / total_tokens) * 100`

**Interpretation:**

| PSI Range | Meaning |
|----------|---------|
| **90–100%** | 🟢 Excellent — the prompt is highly stable; cache efficiency is maximal |
| **75–89%** | 🟡 Good — structure is mostly stable with minor changes |
| **50–74%** | 🟠 Moderate — prompt changes significantly between versions |
| **< 50%** | 🔴 Poor — prompt is unstable; cache reuse is minimal |

---

### **Cache Hit Score**

**Definition:**  
Estimated probability that the prompt will hit the LLM cache.  
Represents the ratio of static tokens to total tokens.

**Formula:**  
`cache_hit_score = static_tokens / total_tokens`

**Interpretation:**

| Score Range | Meaning |
|-------------|---------|
| **0.85–1.0** | 🟢 Excellent — cache will be reused almost every time |
| **0.70–0.84** | 🟡 Good — cache reuse is decent |
| **0.50–0.69** | 🟠 Moderate — cache reuse is inconsistent |
| **< 0.50** | 🔴 Poor — cache is rarely effective |

---

### **Hybrid Similarity**

**Definition:**  
A combined similarity metric using:

- Jaro‑Winkler similarity (character‑level)
- Jaccard similarity (token‑level)

**Formula:**  
`hybrid = 0.5 * jaro_winkler + 0.5 * jaccard`

**Interpretation:**

| Hybrid Range | Meaning |
|--------------|---------|
| **0.85–1.0** | 🟢 Excellent — versions are nearly identical |
| **0.70–0.84** | 🟡 Good — changes are small and localized |
| **0.40–0.69** | 🟠 Moderate — prompt structure changes noticeably |
| **< 0.40** | 🔴 Poor — versions differ significantly |

---

### **Context Drift**

**Definition:**  
Measures how much the **context section only** has changed between versions.

**Formula:**  
`drift = 1 - similarity(context_v1, context_v2)`

**Interpretation:**

| Drift Range | Meaning |
|-------------|---------|
| **0.00–0.05** | 🟢 Excellent — context is stable |
| **0.06–0.20** | 🟡 Moderate — context changes but remains predictable |
| **0.21–0.50** | 🟠 Poor — context is unstable |
| **> 0.50** | 🔴 Very poor — context changes completely |

---

### **Prompt Transitions**

The analyzer builds a transition table:

`v1 -> v2 -> v3 -> …`


For each transition it computes:

- Hybrid Similarity  
- Cache Hit Score  
- Context Drift  

This helps visualize how safely and predictably prompts evolve over time.

---

## Example Output
``` text
Prompt Efficiency Report
Source: promptman_versions
Prompt count: 2
PSI: 91.83
Avg cache hit score: 0.902
Avg similarity (hybrid): 0.8946
Mean context drift: 0.0
```

**Interpretation:**

- PSI 91.83 → 🟢 excellent stability  
- Cache 0.902 → 🟢 cache reuse is nearly perfect  
- Hybrid 0.8946 → 🟢 versions are highly similar  
- Drift 0.0 → 🟢 context did not change at all  

---

## Where These Metrics Are Used

- Prompt version comparison UI  
- API endpoint: `/v1/prompts/{project}/{name}/efficiency`  
- CI/CD quality gates for prompt evolution  
- Prompt rewrite optimization tools  
