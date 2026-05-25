from __future__ import annotations

from collections.abc import Mapping

import tiktoken

from prompt_efficiency_analizer.segmentation import SEGMENT_ORDER


class TokenCounter:
    """Deterministic token counting utility backed by tiktoken."""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self.encoding_name = encoding_name
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count_text(self, text: str) -> int:
        """Count tokens for plain text."""
        return len(self._encoding.encode(text or ""))

    def count_segments(self, segments: Mapping[str, str]) -> dict[str, int]:
        """Count tokens per segment plus total."""
        counts: dict[str, int] = {}
        total = 0
        for key in SEGMENT_ORDER:
            segment_text = str(segments.get(key, "") or "")
            token_count = self.count_text(segment_text)
            counts[key] = token_count
            total += token_count
        counts["total"] = total
        return counts
