from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models import Project, PromptChain, PromptChainVersion

from .common import normalize_project_name
from .project import get_or_create_project


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_chain_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("Prompt chain name is required")
    return value


def _estimate_tokens(content: str) -> int:
    text = (content or "").strip()
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def _compute_reliability_score(content: str) -> float:
    text = (content or "").strip().lower()
    if not text:
        return 0.0

    score = 45.0
    keywords = {"must", "should", "return", "format", "steps", "constraints", "example", "output"}
    hits = sum(1 for key in keywords if key in text)
    score += min(30.0, hits * 4.5)

    line_count = max(1, len([line for line in text.splitlines() if line.strip()]))
    if line_count >= 4:
        score += 8.0
    if len(text) > 400:
        score += 7.0

    ambiguity_markers = ["maybe", "possibly", "approximately", "somehow", "etc"]
    ambiguity_hits = sum(text.count(marker) for marker in ambiguity_markers)
    score -= min(18.0, ambiguity_hits * 3.0)

    return round(max(0.0, min(100.0, score)), 2)


def _compute_cache_hit_probability(content: str) -> float:
    text = (content or "").strip()
    if not text:
        return 0.0

    placeholders = len(re.findall(r"\{\{.*?\}\}|\$\{.*?\}", text))
    placeholder_penalty = min(35.0, placeholders * 3.5)

    digit_count = sum(ch.isdigit() for ch in text)
    symbol_count = sum(ch in "[]{}()<>" for ch in text)
    variability_penalty = min(25.0, (digit_count + symbol_count) / max(1, len(text)) * 200.0)

    sentence_count = max(1, len(re.findall(r"[.!?]", text)))
    structure_bonus = min(18.0, sentence_count * 1.8)

    score = 72.0 + structure_bonus - placeholder_penalty - variability_penalty
    return round(max(0.0, min(100.0, score)), 2)


def compute_prompt_security_metrics(content: str) -> dict[str, float | list[str]]:
    text = (content or "").strip()
    lowered = text.lower()

    injection_markers = [
        "ignore previous",
        "disregard above",
        "ignore all previous",
        "ignore prior",
        "system prompt",
        "hidden prompt",
        "developer mode",
        "reveal hidden",
        "reveal prompt",
        "jailbreak",
        "bypass",
        "do anything now",
        "игнорируй предыдущ",
        "проигнорируй предыдущ",
        "не следуй предыдущ",
        "системный промпт",
        "скрытый промпт",
        "раскрой систем",
        "режим разработчика",
        "джейлбрейк",
        "обойди ограничени",
    ]
    contradiction_pairs = [
        ("always", "never"),
        ("must", "optional"),
        ("strict", "flexible"),
        ("only", "any"),
        ("всегда", "никогда"),
        ("должен", "необязательно"),
        ("обязательно", "опционально"),
        ("только", "любой"),
        ("строго", "гибко"),
    ]
    ambiguity_markers = [
        "maybe",
        "possibly",
        "etc",
        "somehow",
        "approximately",
        "around",
        "perhaps",
        "kind of",
        "more or less",
        "может",
        "возможно",
        "как-нибудь",
        "примерно",
        "около",
        "и т.д",
        "и тп",
        "по возможности",
    ]

    markers: list[str] = []
    injection_hits = 0
    for marker in injection_markers:
        if marker in lowered:
            markers.append(marker)
            injection_hits += 1

    contradiction_hits = 0
    for left, right in contradiction_pairs:
        if left in lowered and right in lowered:
            contradiction_hits += 1
            markers.append(f"{left}<->{right}")

    ambiguity_hits = sum(lowered.count(marker) for marker in ambiguity_markers)

    injection_risk = min(100.0, round(20.0 + injection_hits * 18.0, 2)) if injection_hits else 0.0
    contradiction_risk = min(100.0, round(15.0 + contradiction_hits * 22.0, 2)) if contradiction_hits else 0.0
    ambiguity_risk = min(100.0, round(10.0 + ambiguity_hits * 9.0, 2)) if ambiguity_hits else 0.0

    return {
        "injection_risk": injection_risk,
        "contradiction_risk": contradiction_risk,
        "ambiguity_risk": ambiguity_risk,
        "markers": sorted(set(markers)),
    }


def analyze_prompt_text(content: str) -> dict[str, float | int]:
    tokens = _estimate_tokens(content)
    reliability = _compute_reliability_score(content)
    cache_hit_probability = _compute_cache_hit_probability(content)
    return {
        "tokens": tokens,
        "reliability": reliability,
        "cache_hit_probability": cache_hit_probability,
    }


def create_prompt_chain(
    db: Session,
    *,
    project: str,
    name: str,
    description: str | None,
    initial_content: str,
    notes: str | None,
    actor_id: int | None,
) -> PromptChain:
    project_name = normalize_project_name(project)
    chain_name = _normalize_chain_name(name)
    existing = (
        db.query(PromptChain)
        .join(PromptChain.project_ref)
        .filter(func.lower(Project.name) == project_name.lower(), func.lower(PromptChain.name) == chain_name.lower())
        .first()
    )
    if existing:
        raise ValueError("Prompt chain already exists in project")

    project_record = get_or_create_project(db, project_name)
    now = _utcnow()
    chain = PromptChain(
        project_ref=project_record,
        name=chain_name,
        description=(description or "").strip() or None,
        created_at=now,
        updated_at=now,
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    db.add(chain)
    db.flush()

    version = PromptChainVersion(
        chain_ref=chain,
        version_no=1,
        content=(initial_content or "").strip(),
        notes=(notes or "").strip() or None,
        created_at=now,
        created_by_id=actor_id,
    )
    db.add(version)
    db.commit()
    db.refresh(chain)
    return chain


def list_prompt_chains(
    db: Session,
    *,
    project: str | None = None,
    allowed_projects: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PromptChain]:
    query = (
        db.query(PromptChain)
        .join(PromptChain.project_ref)
        .options(
            joinedload(PromptChain.project_ref),
            joinedload(PromptChain.created_by_ref),
            joinedload(PromptChain.updated_by_ref),
        )
    )

    if allowed_projects is not None:
        if not allowed_projects:
            return []
        query = query.filter(Project.name.in_(allowed_projects))

    if project:
        query = query.filter(func.lower(Project.name) == normalize_project_name(project).lower())

    rows = (
        query.order_by(PromptChain.updated_at.desc(), PromptChain.id.desc())
        .offset(max(0, offset))
        .limit(max(1, limit))
        .all()
    )
    return list(rows)


def get_prompt_chain_by_id(db: Session, chain_id: int, *, allowed_projects: list[str] | None = None) -> PromptChain | None:
    query = (
        db.query(PromptChain)
        .join(PromptChain.project_ref)
        .options(
            joinedload(PromptChain.project_ref),
            joinedload(PromptChain.created_by_ref),
            joinedload(PromptChain.updated_by_ref),
        )
        .filter(PromptChain.id == chain_id)
    )
    if allowed_projects is not None:
        if not allowed_projects:
            return None
        query = query.filter(Project.name.in_(allowed_projects))
    return query.first()


def list_prompt_chain_versions(db: Session, chain_id: int) -> list[PromptChainVersion]:
    rows = (
        db.query(PromptChainVersion)
        .options(joinedload(PromptChainVersion.created_by_ref))
        .filter(PromptChainVersion.chain_id == chain_id)
        .order_by(PromptChainVersion.version_no.asc())
        .all()
    )
    return list(rows)


def get_prompt_chain_version(db: Session, chain_id: int, version_no: int) -> PromptChainVersion | None:
    return (
        db.query(PromptChainVersion)
        .options(joinedload(PromptChainVersion.created_by_ref))
        .filter(PromptChainVersion.chain_id == chain_id, PromptChainVersion.version_no == version_no)
        .first()
    )


def add_prompt_chain_version(
    db: Session,
    *,
    chain: PromptChain,
    content: str,
    notes: str | None,
    actor_id: int | None,
) -> PromptChainVersion:
    latest_row = (
        db.query(PromptChainVersion.version_no)
        .filter(PromptChainVersion.chain_id == chain.id)
        .order_by(PromptChainVersion.version_no.desc())
        .first()
    )
    next_version = int(latest_row[0]) + 1 if latest_row else 1
    now = _utcnow()

    version_row = PromptChainVersion(
        chain_id=chain.id,
        version_no=next_version,
        content=(content or "").strip(),
        notes=(notes or "").strip() or None,
        created_at=now,
        created_by_id=actor_id,
    )
    db.add(version_row)

    chain.updated_at = now
    chain.updated_by_id = actor_id
    db.add(chain)

    db.commit()
    db.refresh(version_row)
    return version_row


def build_chain_analysis_report(versions: list[PromptChainVersion]) -> dict[str, object]:
    points: list[dict[str, object]] = []
    prev_tokens = 0
    prev_reliability = 0.0
    prev_cache = 0.0
    prev_injection = 0.0
    prev_contradiction = 0.0
    prev_ambiguity = 0.0

    for index, row in enumerate(versions):
        metrics = analyze_prompt_text(row.content)
        security = compute_prompt_security_metrics(row.content)
        tokens = int(metrics["tokens"])
        reliability = float(metrics["reliability"])
        cache_hit = float(metrics["cache_hit_probability"])
        injection_risk = float(security["injection_risk"])
        contradiction_risk = float(security["contradiction_risk"])
        ambiguity_risk = float(security["ambiguity_risk"])

        points.append(
            {
                "version_no": row.version_no,
                "tokens": tokens,
                "reliability": reliability,
                "cache_hit_probability": cache_hit,
                "injection_risk": injection_risk,
                "contradiction_risk": contradiction_risk,
                "ambiguity_risk": ambiguity_risk,
                "delta_tokens": 0 if index == 0 else tokens - prev_tokens,
                "delta_reliability": 0.0 if index == 0 else round(reliability - prev_reliability, 2),
                "delta_cache_hit": 0.0 if index == 0 else round(cache_hit - prev_cache, 2),
                "delta_injection_risk": 0.0 if index == 0 else round(injection_risk - prev_injection, 2),
                "delta_contradiction_risk": 0.0 if index == 0 else round(contradiction_risk - prev_contradiction, 2),
                "delta_ambiguity_risk": 0.0 if index == 0 else round(ambiguity_risk - prev_ambiguity, 2),
            }
        )

        prev_tokens = tokens
        prev_reliability = reliability
        prev_cache = cache_hit
        prev_injection = injection_risk
        prev_contradiction = contradiction_risk
        prev_ambiguity = ambiguity_risk

    avg_tokens = round(sum(point["tokens"] for point in points) / max(1, len(points)), 2)
    avg_reliability = round(sum(point["reliability"] for point in points) / max(1, len(points)), 2)
    avg_cache_hit = round(sum(point["cache_hit_probability"] for point in points) / max(1, len(points)), 2)
    avg_injection_risk = round(sum(point["injection_risk"] for point in points) / max(1, len(points)), 2)
    avg_contradiction_risk = round(sum(point["contradiction_risk"] for point in points) / max(1, len(points)), 2)
    avg_ambiguity_risk = round(sum(point["ambiguity_risk"] for point in points) / max(1, len(points)), 2)

    trend_tokens = 0
    trend_reliability = 0.0
    trend_cache_hit = 0.0
    trend_injection_risk = 0.0
    trend_contradiction_risk = 0.0
    trend_ambiguity_risk = 0.0
    if len(points) >= 2:
        trend_tokens = int(points[-1]["tokens"]) - int(points[0]["tokens"])
        trend_reliability = round(float(points[-1]["reliability"]) - float(points[0]["reliability"]), 2)
        trend_cache_hit = round(float(points[-1]["cache_hit_probability"]) - float(points[0]["cache_hit_probability"]), 2)
        trend_injection_risk = round(float(points[-1]["injection_risk"]) - float(points[0]["injection_risk"]), 2)
        trend_contradiction_risk = round(float(points[-1]["contradiction_risk"]) - float(points[0]["contradiction_risk"]), 2)
        trend_ambiguity_risk = round(float(points[-1]["ambiguity_risk"]) - float(points[0]["ambiguity_risk"]), 2)

    return {
        "points": points,
        "summary": {
            "versions": len(points),
            "average_tokens": avg_tokens,
            "average_reliability": avg_reliability,
            "average_cache_hit_probability": avg_cache_hit,
            "average_injection_risk": avg_injection_risk,
            "average_contradiction_risk": avg_contradiction_risk,
            "average_ambiguity_risk": avg_ambiguity_risk,
            "trend_tokens": trend_tokens,
            "trend_reliability": trend_reliability,
            "trend_cache_hit_probability": trend_cache_hit,
            "trend_injection_risk": trend_injection_risk,
            "trend_contradiction_risk": trend_contradiction_risk,
            "trend_ambiguity_risk": trend_ambiguity_risk,
        },
    }
