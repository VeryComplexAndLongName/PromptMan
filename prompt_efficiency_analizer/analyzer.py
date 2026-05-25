from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import requests

from prompt_efficiency_analizer.cache_estimator import compute_prompt_stability_index, estimate_cache_hit_score
from prompt_efficiency_analizer.drift import analyze_context_drift, context_change_ratio
from prompt_efficiency_analizer.report import build_markdown_report, build_rich_report_text
from prompt_efficiency_analizer.segmentation import compose_prompt_text, segment_prompt
from prompt_efficiency_analizer.similarity import compute_similarity
from prompt_efficiency_analizer.token_counter import TokenCounter


@dataclass(slots=True)
class PromptSnapshot:
    """Normalized prompt sample for analysis."""

    label: str
    role: str = ""
    task: str = ""
    context: str = ""
    constraints: str = ""
    output_format: str = ""
    examples: str = ""

    def as_prompt_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "task": self.task,
            "context": self.context,
            "constraints": self.constraints,
            "output_format": self.output_format,
            "examples": self.examples,
        }


class PromptEfficiencyAnalyzer:
    """High-level API for deterministic prompt efficiency analysis without LLM usage."""

    def __init__(self, encoding_name: str = "cl100k_base", request_timeout_seconds: float = 15.0) -> None:
        self.encoding_name = encoding_name
        self.request_timeout_seconds = request_timeout_seconds
        self._counter = TokenCounter(encoding_name=encoding_name)

    def analyze_prompt_chain(self, prompts: Sequence[Mapping[str, object]], source: str = "json_chain") -> dict[str, object]:
        """Analyze a sequence of PromptMan-compatible payloads."""
        snapshots = self._normalize_payloads(prompts)
        return self._analyze_snapshots(snapshots, source=source)

    def analyze_prompt_chain_json(self, payload: str) -> dict[str, object]:
        """Parse JSON payload with prompt chain and analyze it."""
        parsed = json.loads(payload)
        if isinstance(parsed, dict) and isinstance(parsed.get("prompts"), list):
            prompts = parsed["prompts"]
        elif isinstance(parsed, list):
            prompts = parsed
        else:
            raise ValueError("JSON chain must be a list or an object with 'prompts' list")
        return self.analyze_prompt_chain(prompts, source="json_chain")

    def analyze_promptman_prompt(
        self,
        *,
        base_url: str,
        project: str,
        prompt_name: str,
        version_selector: str = "all",
        access_token: str | None = None,
        verify_tls: bool = True,
    ) -> dict[str, object]:
        """Load prompt versions from PromptMan REST API and analyze them."""
        snapshots = self._fetch_promptman_versions(
            base_url=base_url,
            project=project,
            prompt_name=prompt_name,
            version_selector=version_selector,
            access_token=access_token,
            verify_tls=verify_tls,
        )
        return self._analyze_snapshots(snapshots, source="promptman_versions")

    def _normalize_payloads(self, prompts: Sequence[Mapping[str, object]]) -> list[PromptSnapshot]:
        snapshots: list[PromptSnapshot] = []
        for index, raw in enumerate(prompts, start=1):
            label = str(raw.get("label") or raw.get("version") or f"item-{index}")
            snapshots.append(
                PromptSnapshot(
                    label=label,
                    role=str(raw.get("role") or ""),
                    task=str(raw.get("task") or ""),
                    context=str(raw.get("context") or ""),
                    constraints=str(raw.get("constraints") or ""),
                    output_format=str(raw.get("output_format") or ""),
                    examples=str(raw.get("examples") or ""),
                )
            )
        if len(snapshots) < 1:
            raise ValueError("At least one prompt is required")
        return snapshots

    def _fetch_promptman_versions(
        self,
        *,
        base_url: str,
        project: str,
        prompt_name: str,
        version_selector: str,
        access_token: str | None,
        verify_tls: bool,
    ) -> list[PromptSnapshot]:
        base = base_url.rstrip("/")
        headers: dict[str, str] = {"Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token.strip()}"

        list_url = f"{base}/v1/prompts/{project}/{prompt_name}/versions"
        response = requests.get(list_url, headers=headers, timeout=self.request_timeout_seconds, verify=verify_tls)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected PromptMan versions response")

        requested_versions = self._parse_version_selector(version_selector, available_versions=[item.get("version") for item in payload])
        selected = [item for item in payload if int(item.get("version", 0)) in requested_versions]
        if not selected:
            raise ValueError("No prompt versions matched the selector")

        snapshots: list[PromptSnapshot] = []
        for item in selected:
            version_value = int(item.get("version", 0))
            snapshots.append(
                PromptSnapshot(
                    label=f"v{version_value}",
                    role=str(item.get("role") or ""),
                    task=str(item.get("task") or ""),
                    context=str(item.get("context") or ""),
                    constraints=str(item.get("constraints") or ""),
                    output_format=str(item.get("output_format") or ""),
                    examples=str(item.get("examples") or ""),
                )
            )
        snapshots.sort(key=lambda snapshot: int(snapshot.label.replace("v", "")) if snapshot.label.startswith("v") else 0)
        return snapshots

    def _parse_version_selector(self, selector: str, available_versions: Iterable[object]) -> set[int]:
        versions = sorted({int(value) for value in available_versions if isinstance(value, int) or str(value).isdigit()})
        if not versions:
            return set()
        normalized = (selector or "all").strip().lower()
        if normalized in {"", "all", "*"}:
            return set(versions)

        result: set[int] = set()
        for chunk in normalized.split(","):
            part = chunk.strip()
            if not part:
                continue
            if "-" in part:
                left, right = part.split("-", maxsplit=1)
                if not left.isdigit() or not right.isdigit():
                    continue
                start, end = int(left), int(right)
                if start > end:
                    start, end = end, start
                for version in versions:
                    if start <= version <= end:
                        result.add(version)
                continue
            if part.isdigit():
                result.add(int(part))

        return result if result else set(versions)

    def _analyze_snapshots(self, snapshots: Sequence[PromptSnapshot], source: str) -> dict[str, object]:
        segmented = [segment_prompt(snapshot.as_prompt_dict()) for snapshot in snapshots]
        token_stats = [self._counter.count_segments(item) for item in segmented]

        prompts_section: list[dict[str, object]] = []
        for index, snapshot in enumerate(snapshots):
            prompts_section.append(
                {
                    "label": snapshot.label,
                    "segments": segmented[index],
                    "token_counts": token_stats[index],
                    "prompt_text": compose_prompt_text(segmented[index]),
                }
            )

        transitions: list[dict[str, object]] = []
        pairwise_hybrid: list[float] = []
        cache_scores: list[float] = []
        context_series: list[str] = [item.get("context", "") for item in segmented]

        for index in range(1, len(prompts_section)):
            prev_item = prompts_section[index - 1]
            current_item = prompts_section[index]
            similarity = compute_similarity(str(prev_item["prompt_text"]), str(current_item["prompt_text"]))
            cache_hit_score = estimate_cache_hit_score(prev_item["segments"], current_item["segments"])  # type: ignore[arg-type]
            drift = context_change_ratio(
                str(prev_item["segments"].get("context", "")),  # type: ignore[union-attr]
                str(current_item["segments"].get("context", "")),  # type: ignore[union-attr]
            )
            pairwise_hybrid.append(similarity["hybrid"])
            cache_scores.append(cache_hit_score)
            transitions.append(
                {
                    "from_label": prev_item["label"],
                    "to_label": current_item["label"],
                    "levenshtein": round(similarity["levenshtein"], 4),
                    "jaro_winkler": round(similarity["jaro_winkler"], 4),
                    "jaccard": round(similarity["jaccard"], 4),
                    "hybrid_similarity": round(similarity["hybrid"], 4),
                    "cache_hit_score": round(cache_hit_score, 4),
                    "context_drift": round(drift, 4),
                }
            )

        drift_stats = analyze_context_drift(context_series)
        psi = compute_prompt_stability_index(pairwise_hybrid, cache_scores, float(drift_stats["mean"]))

        summary = {
            "source": source,
            "prompt_count": len(prompts_section),
            "psi": psi,
            "avg_cache_hit_score": round(sum(cache_scores) / len(cache_scores), 4) if cache_scores else 1.0,
            "avg_hybrid_similarity": round(sum(pairwise_hybrid) / len(pairwise_hybrid), 4) if pairwise_hybrid else 1.0,
            "context_drift_mean": drift_stats["mean"],
            "context_drift_max": drift_stats["max"],
            "encoding": self.encoding_name,
        }

        result: dict[str, object] = {
            "summary": summary,
            "prompts": prompts_section,
            "transitions": transitions,
            "context_drift": drift_stats,
        }
        result["markdown_report"] = build_markdown_report(result)
        result["rich_report"] = build_rich_report_text(result)
        return result
