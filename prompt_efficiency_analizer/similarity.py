from __future__ import annotations

import re
from collections.abc import Iterable

from rapidfuzz.distance import JaroWinkler, Levenshtein

_TOKEN_REGEX = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_REGEX.findall((text or "").lower())


def jaccard_similarity(left_tokens: Iterable[str], right_tokens: Iterable[str]) -> float:
    """Compute Jaccard similarity over token sets in range [0, 1]."""
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def compute_similarity(left_text: str, right_text: str) -> dict[str, float]:
    """Compute deterministic lexical similarity metrics without heavy ML dependencies."""
    left = left_text or ""
    right = right_text or ""
    lev = float(Levenshtein.normalized_similarity(left, right))
    jaro = float(JaroWinkler.normalized_similarity(left, right))
    jaccard = jaccard_similarity(_tokenize(left), _tokenize(right))
    hybrid = (0.45 * lev) + (0.35 * jaro) + (0.20 * jaccard)
    return {
        "levenshtein": lev,
        "jaro_winkler": jaro,
        "jaccard": jaccard,
        "hybrid": hybrid,
    }
