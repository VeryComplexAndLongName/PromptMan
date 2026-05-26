from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence

from prompt_efficiency_analizer.segmentation import SEGMENT_ORDER
from prompt_efficiency_analizer.similarity import compute_similarity

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_\-.]*)\s*\}\}|\{\s*([a-zA-Z_][a-zA-Z0-9_\-.]*)\s*\}|<\s*([a-zA-Z_][a-zA-Z0-9_\-.]*)\s*>|\$([a-zA-Z_][a-zA-Z0-9_]*)|%%\s*([a-zA-Z_][a-zA-Z0-9_\-.]*)\s*%%")

_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmust\b"),
    re.compile(r"\bmust not\b"),
    re.compile(r"\bnever\b"),
    re.compile(r"\balways\b"),
    re.compile(r"\bonly\b"),
    re.compile(r"\bexactly\b"),
    re.compile(r"\brequired\b"),
    re.compile(r"\bdo not\b"),
)

_AMBIGUITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bmaybe\b"),
    re.compile(r"\bperhaps\b"),
    re.compile(r"\bsomehow\b"),
    re.compile(r"\baround\b"),
    re.compile(r"\bapproximately\b"),
    re.compile(r"\betc\.?\b"),
    re.compile(r"\boptional\b"),
    re.compile(r"\bif possible\b"),
)

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+previous\s+instructions"),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt"),
    re.compile(r"show\s+(the\s+)?developer\s+message"),
    re.compile(r"bypass\s+safety"),
    re.compile(r"jailbreak"),
    re.compile(r"\bdan\b"),
    re.compile(r"override\s+instructions"),
)

_CONFLICT_PAIRS: tuple[tuple[str, str], ...] = (
    ("must", "must not"),
    ("always", "never"),
    ("use", "do not use"),
    ("include", "do not include"),
    ("json", "plain text"),
)

_OUTPUT_KEYWORDS: tuple[str, ...] = (
    "json",
    "yaml",
    "xml",
    "markdown",
    "table",
    "csv",
    "schema",
    "fields",
    "keys",
    "format",
    "bullet",
    "list",
)

_DEFAULT_CONTEXT_WINDOW_BY_ENCODING: dict[str, int] = {
    "cl100k_base": 128000,
    "o200k_base": 200000,
    "p50k_base": 8192,
    "r50k_base": 4096,
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _word_tokens(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _count_pattern_hits(text: str, patterns: Sequence[re.Pattern[str]]) -> int:
    lowered = (text or "").lower()
    return sum(len(pattern.findall(lowered)) for pattern in patterns)


def extract_placeholders(text: str) -> set[str]:
    names: set[str] = set()
    for match in _PLACEHOLDER_RE.finditer(text or ""):
        groups = [item for item in match.groups() if item]
        if groups:
            names.add(groups[0].strip().lower())
    return names


def segment_volatility(previous_segments: Mapping[str, str], current_segments: Mapping[str, str]) -> dict[str, float]:
    volatility: dict[str, float] = {}
    for key in SEGMENT_ORDER:
        left = str(previous_segments.get(key, "") or "")
        right = str(current_segments.get(key, "") or "")
        similarity = compute_similarity(left, right)["hybrid"]
        volatility[key] = round(_clamp(1.0 - similarity), 4)
    return volatility


def placeholder_stability(previous_text: str, current_text: str) -> dict[str, object]:
    left = extract_placeholders(previous_text)
    right = extract_placeholders(current_text)
    union = left | right
    intersection = left & right
    stability = 1.0 if not union else len(intersection) / len(union)
    return {
        "stability": round(_clamp(stability), 4),
        "added": sorted(right - left),
        "removed": sorted(left - right),
        "count_previous": len(left),
        "count_current": len(right),
    }


def constraint_strictness_score(text: str) -> float:
    tokens = _word_tokens(text)
    token_count = max(len(tokens), 1)
    strict_hits = _count_pattern_hits(text, _STRICT_PATTERNS)
    normalized = (strict_hits / token_count) * 18.0
    return round(_clamp(normalized), 4)


def ambiguity_score(text: str) -> float:
    tokens = _word_tokens(text)
    token_count = max(len(tokens), 1)
    ambiguity_hits = _count_pattern_hits(text, _AMBIGUITY_PATTERNS)
    normalized = (ambiguity_hits / token_count) * 20.0
    return round(_clamp(normalized), 4)


def output_schema_compliance_score(text: str) -> float:
    lowered = (text or "").lower()
    keyword_hits = sum(1 for key in _OUTPUT_KEYWORDS if key in lowered)
    keyword_component = _clamp(keyword_hits / 4.0)

    structure_hits = 0
    if re.search(r"\{\s*\"[a-zA-Z0-9_\-]+\"\s*:", text or ""):
        structure_hits += 1
    if re.search(r"^#+\s+", text or "", flags=re.MULTILINE):
        structure_hits += 1
    if "```" in (text or ""):
        structure_hits += 1
    if re.search(r"\|.+\|", text or ""):
        structure_hits += 1
    if re.search(r"\b\d+[\.)]\s+", text or ""):
        structure_hits += 1
    structure_component = _clamp(structure_hits / 3.0)

    score = (0.55 * keyword_component) + (0.45 * structure_component)
    return round(_clamp(score), 4)


def redundancy_ratio(text: str) -> float:
    tokens = _word_tokens(text)
    if len(tokens) < 2:
        return 0.0

    unique_ratio = len(set(tokens)) / len(tokens)
    bigrams = [f"{tokens[i]}::{tokens[i + 1]}" for i in range(len(tokens) - 1)]
    counts = Counter(bigrams)
    repeated = sum(value - 1 for value in counts.values() if value > 1)
    repeated_bigram_ratio = repeated / max(len(bigrams), 1)

    score = ((1.0 - unique_ratio) * 0.70) + (repeated_bigram_ratio * 0.30)
    return round(_clamp(score), 4)


def instruction_conflict_risk(text: str) -> dict[str, object]:
    lowered = (text or "").lower()
    conflicts: list[str] = []

    for positive, negative in _CONFLICT_PAIRS:
        if positive in lowered and negative in lowered:
            conflicts.append(f"{positive} <-> {negative}")

    exact_values = re.findall(r"exactly\s+(\d+)", lowered)
    if len(set(exact_values)) > 1:
        conflicts.append("multiple distinct 'exactly N' constraints")

    risk = _clamp(len(conflicts) / 3.0)
    return {
        "risk": round(risk, 4),
        "conflicts": conflicts,
    }


def injection_surface_score(text: str) -> dict[str, object]:
    lowered = (text or "").lower()
    matched: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(lowered):
            matched.append(pattern.pattern)
    score = _clamp(len(matched) / 3.0)
    return {
        "score": round(score, 4),
        "matched_patterns": matched,
    }


def readability_difficulty_score(text: str) -> float:
    content = (text or "").strip()
    if not content:
        return 0.0

    sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(content) if item.strip()]
    words = _word_tokens(content)
    avg_sentence_len = (len(words) / max(len(sentences), 1)) if words else 0.0

    long_sentence_component = _clamp((avg_sentence_len - 14.0) / 18.0)
    symbol_density = _clamp(len(re.findall(r"[:;()\[\]{}]", content)) / max(len(content), 1) * 20.0)
    nesting_matches = re.findall(r"\n\s*[-*]|\n\s*\d+[\.)]", content)
    nesting_signal = _clamp(len(nesting_matches) / 12.0)

    score = (0.50 * long_sentence_component) + (0.30 * symbol_density) + (0.20 * nesting_signal)
    return round(_clamp(score), 4)


def token_budget_metrics(total_tokens: int, encoding_name: str, context_window_tokens: int | None = None) -> dict[str, object]:
    budget = context_window_tokens or _DEFAULT_CONTEXT_WINDOW_BY_ENCODING.get(encoding_name, 128000)
    total = max(int(total_tokens), 0)
    remaining = budget - total
    usage_ratio = _clamp(total / budget) if budget > 0 else 1.0
    safety_ratio = _clamp(remaining / budget) if budget > 0 else 0.0
    return {
        "context_window_tokens": budget,
        "total_tokens": total,
        "remaining_tokens": remaining,
        "usage_ratio": round(usage_ratio, 4),
        "safety_ratio": round(safety_ratio, 4),
        "is_over_budget": remaining < 0,
    }


def compute_prompt_quality_metrics(
    *,
    segments: Mapping[str, str],
    prompt_text: str,
    token_counts: Mapping[str, int],
    encoding_name: str,
    context_window_tokens: int | None = None,
) -> dict[str, object]:
    constraints = str(segments.get("constraints", "") or "")
    output_format = str(segments.get("output_format", "") or "")
    examples = str(segments.get("examples", "") or "")

    strictness = constraint_strictness_score(constraints)
    ambiguity = ambiguity_score(prompt_text)
    output_schema = output_schema_compliance_score(output_format)
    redundancy = redundancy_ratio(prompt_text)
    conflict = instruction_conflict_risk(prompt_text)
    injection = injection_surface_score(f"{segments.get('context', '')}\n{examples}")
    readability = readability_difficulty_score(prompt_text)
    placeholders = extract_placeholders(prompt_text)
    budget = token_budget_metrics(int(token_counts.get("total", 0)), encoding_name, context_window_tokens)

    return {
        "constraint_strictness": strictness,
        "ambiguity": ambiguity,
        "output_schema_compliance": output_schema,
        "redundancy": redundancy,
        "instruction_conflict_risk": conflict["risk"],
        "instruction_conflicts": conflict["conflicts"],
        "injection_surface_score": injection["score"],
        "injection_matched_patterns": injection["matched_patterns"],
        "readability_difficulty": readability,
        "placeholder_count": len(placeholders),
        "placeholders": sorted(placeholders),
        "token_budget": budget,
    }
