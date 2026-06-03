from __future__ import annotations

import json
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener, urlopen
from urllib.request import Request as UrlRequest
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

import app_settings
import auth as auth_service
import crud
from app_core.api_version import API_V1
from database import get_db, run_db_call
from schemas import (
    PromptChainAnalysisOut,
    PromptChainCreate,
    PromptChainOut,
    PromptChainVersionCreate,
    PromptChainVersionOut,
    PromptOrchestratorPreviewOut,
    PromptTestRunOut,
    PromptVersionAnalysisOut,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from models import User

router = APIRouter(prefix=f"{API_V1}/prompt-versions", tags=["Prompt Versions"])
PROMPT_ORCHESTRATOR_LOG_ROOT = Path("logs") / "prompt-orchestrator"

_PROMPT_TEST_RUNS: deque[dict[str, object]] = deque(maxlen=500)
_PROMPT_TEST_RUNS_LOCK = Lock()
_VARIABLE_PATTERN = re.compile(r"\{\{.*?\}\}|\$\{.*?\}|\{[A-Za-z_][^{}\n]*\}")
_WORD_PATTERN = re.compile(r"[A-Za-z0-9_\u00C0-\u024F\u0400-\u04FF]+")


def _http_post_json(
    url: str,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 8.0,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = UrlRequest(url, data=body, headers=request_headers, method="POST")

    host = (urlparse(url).hostname or "").lower()
    bypass_proxy = host in {"localhost", "::1"} or host.startswith("127.")

    try:
        if bypass_proxy:
            opener = build_opener(ProxyHandler({}))
            response_ctx = opener.open(request, timeout=timeout_seconds)
        else:
            response_ctx = urlopen(request, timeout=timeout_seconds)
        with response_ctx as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {}


def _invoke_live_llm(full_prompt: str) -> dict[str, object]:
    return _invoke_profiled_llm(full_prompt, profile="test")


def _resolve_profile_llm_config(profile: str) -> dict[str, object]:
    profile_name = (profile or "test").strip().lower()

    if profile_name == "optimizer":
        return {
            "provider": app_settings.get("OPTIMIZER_PROVIDER", "openai").strip().lower(),
            "model": app_settings.get("OPTIMIZER_MODEL", "").strip(),
            "backend": app_settings.get("OPTIMIZER_BACKEND", "leo").strip() or "leo",
            "base_url": app_settings.get("OPTIMIZER_BASE_URL", "").strip(),
            "token": app_settings.get("OPTIMIZER_API_TOKEN", "").strip(),
            "timeout_seconds": app_settings.get_int("OPTIMIZER_TIMEOUT_SECONDS", 30),
            "profile": "optimizer",
        }

    if profile_name == "compression":
        return {
            "provider": app_settings.get("PROMPT_COMPRESSION_PROVIDER", "openai").strip().lower(),
            "model": app_settings.get("PROMPT_COMPRESSION_MODEL", "").strip(),
            "backend": app_settings.get("PROMPT_COMPRESSION_BACKEND", "leo").strip() or "leo",
            "base_url": app_settings.get("PROMPT_COMPRESSION_BASE_URL", "").strip(),
            "token": app_settings.get("PROMPT_COMPRESSION_API_TOKEN", "").strip(),
            "timeout_seconds": app_settings.get_int("OPTIMIZER_TIMEOUT_SECONDS", 30),
            "profile": "compression",
        }

    provider = app_settings.get("TEST_LLM_PROVIDER", "").strip().lower()
    model = app_settings.get("TEST_LLM_MODEL", "").strip()
    backend = app_settings.get("OPTIMIZER_BACKEND", "leo").strip() or "leo"
    base_url = app_settings.get("TEST_LLM_BASE_URL", "").strip()
    token = app_settings.get("TEST_LLM_API_TOKEN", "").strip()
    timeout_seconds = app_settings.get_int("TEST_LLM_TIMEOUT_SECONDS", 30)

    use_optimizer_fallback = app_settings.get_bool("TEST_LLM_USE_OPTIMIZER_FALLBACK", True)
    if use_optimizer_fallback:
        provider = provider or app_settings.get("OPTIMIZER_PROVIDER", "openai").strip().lower()
        model = model or app_settings.get("OPTIMIZER_MODEL", "").strip()
        base_url = base_url or app_settings.get("OPTIMIZER_BASE_URL", "").strip()
        token = token or app_settings.get("OPTIMIZER_API_TOKEN", "").strip()

    return {
        "provider": provider,
        "model": model,
        "backend": backend,
        "base_url": base_url,
        "token": token,
        "timeout_seconds": timeout_seconds,
        "profile": "test",
    }


def _invoke_profiled_llm(full_prompt: str, *, profile: str = "test") -> dict[str, object]:
    config = _resolve_profile_llm_config(profile)
    provider = str(config.get("provider", "")).strip().lower()
    model = str(config.get("model", "")).strip()
    backend = str(config.get("backend", "leo")).strip() or "leo"
    base_url = str(config.get("base_url", "")).strip()
    token = str(config.get("token", "")).strip()
    timeout_seconds = int(config.get("timeout_seconds", 30) or 30)

    if not base_url:
        default_map = {
            "openai": "https://api.openai.com/v1",
            "ollama": "http://127.0.0.1:11434",
        }
        base_url = default_map.get(provider, "")

    llm_snapshot = {
        "provider": provider,
        "model": model,
        "backend": backend,
        "base_url": base_url or None,
        "llm_invoked": False,
    }

    if not model or not base_url:
        return {
            "llm": llm_snapshot,
            "response_text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_error": "Model/base URL is not configured",
        }

    if provider == "openai" and not token:
        return {
            "llm": llm_snapshot,
            "response_text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_error": "OpenAI API token is missing",
        }

    response_payload: dict[str, object] = {}
    if provider == "openai":
        response_payload = _http_post_json(
            f"{base_url.rstrip('/')}/chat/completions",
            {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": full_prompt,
                    }
                ],
                "temperature": 0,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout_seconds=max(3, timeout_seconds),
        )
        choices = response_payload.get("choices", []) if isinstance(response_payload, dict) else []
        message = choices[0].get("message", {}) if choices else {}
        usage = response_payload.get("usage", {}) if isinstance(response_payload, dict) else {}
        llm_snapshot["llm_invoked"] = bool(choices)
        return {
            "llm": llm_snapshot,
            "response_text": str(message.get("content", "")),
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "llm_error": "" if choices else "OpenAI returned no choices",
        }

    if provider == "ollama":
        response_payload = _http_post_json(
            f"{base_url.rstrip('/')}/api/generate",
            {
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout_seconds=max(3, timeout_seconds),
        )
        llm_snapshot["llm_invoked"] = bool(response_payload.get("response"))
        prompt_tokens = int(response_payload.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(response_payload.get("eval_count", 0) or 0)
        total_tokens = prompt_tokens + completion_tokens
        return {
            "llm": llm_snapshot,
            "response_text": str(response_payload.get("response", "")),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "llm_error": "" if llm_snapshot["llm_invoked"] else "Ollama returned empty response",
        }

    return {
        "llm": llm_snapshot,
        "response_text": "",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "llm_error": f"Unsupported provider: {provider}",
    }


def _tokenize_words(text: str) -> set[str]:
    return {token.lower() for token in _WORD_PATTERN.findall(text or "")}


def _read_rag_chunks(source_path: str, top_k: int, query: str) -> list[str]:
    file_path = Path(source_path)
    if not file_path.exists() or not file_path.is_file():
        return []

    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    sections = [chunk.strip() for chunk in re.split(r"\n\s*\n", raw) if chunk.strip()]
    if not sections:
        return []

    query_tokens = _tokenize_words(query)
    if not query_tokens:
        return sections[: max(1, top_k)]

    scored: list[tuple[int, str]] = []
    for section in sections:
        score = len(_tokenize_words(section) & query_tokens)
        scored.append((score, section))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [text for score, text in scored if score > 0][: max(1, top_k)]
    return selected or sections[: max(1, top_k)]


def _build_prompt_with_rag(content: str) -> tuple[str, dict[str, object]]:
    rag_enabled = app_settings.get_bool("TEST_RAG_ENABLED", False)
    source_path = app_settings.get("TEST_RAG_SOURCE_PATH", "simulations/rag_knowledge.md").strip()
    top_k = max(1, app_settings.get_int("TEST_RAG_TOP_K", 3))

    if not rag_enabled:
        return content, {"enabled": False, "source_path": source_path or None, "top_k": top_k, "chunks": []}

    chunks = _read_rag_chunks(source_path, top_k, content)
    if not chunks:
        return content, {"enabled": True, "source_path": source_path or None, "top_k": top_k, "chunks": []}

    rag_context = "\n\n".join([f"[RAG {idx + 1}] {chunk}" for idx, chunk in enumerate(chunks)])
    prompt_with_rag = (
        f"{content.strip()}\n\n"
        "Use the following retrieved context when relevant:\n"
        f"{rag_context}\n"
    )
    return prompt_with_rag, {
        "enabled": True,
        "source_path": source_path or None,
        "top_k": top_k,
        "chunks": chunks,
    }


def _allowed_projects(current_user: User) -> list[str] | None:
    return auth_service.allowed_projects_for_user(current_user)


def _to_iso(value) -> str:  # type: ignore[no-untyped-def]
    dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return dt.isoformat()


def _extract_prompt_breakdown(content: str) -> dict[str, object]:
    text = (content or "").strip()
    lines = text.splitlines()

    variables = _VARIABLE_PATTERN.findall(text)
    unique_variables = sorted(set(variables))

    fixed_lines = [line for line in lines if not _VARIABLE_PATTERN.search(line)]
    semi_fixed_lines = [line for line in lines if _VARIABLE_PATTERN.search(line)]

    fixed_part = "\n".join(fixed_lines).strip()
    semi_fixed_part = "\n".join(semi_fixed_lines).strip()
    variable_part = "\n".join(unique_variables).strip()

    return {
        "fixed_part": fixed_part,
        "semi_fixed_part": semi_fixed_part,
        "variable_part": variable_part,
        "variables": unique_variables,
    }


def _build_prompt_test_run(chain, version, current_user: User) -> dict[str, object]:  # type: ignore[no-untyped-def]
    started = perf_counter()
    prompt_with_rag, rag_info = _build_prompt_with_rag(version.content)
    metrics = crud.analyze_prompt_text(prompt_with_rag)
    live = _invoke_live_llm(prompt_with_rag)
    security = crud.compute_prompt_security_metrics(prompt_with_rag)
    elapsed_ms = round((perf_counter() - started) * 1000, 2)

    breakdown = _extract_prompt_breakdown(prompt_with_rag)
    estimated_prompt_tokens = int(metrics["tokens"])
    prompt_tokens = int(live.get("prompt_tokens", 0) or 0)
    completion_tokens = int(live.get("completion_tokens", 0) or 0)
    total_tokens = int(live.get("total_tokens", 0) or 0)

    if prompt_tokens <= 0:
        prompt_tokens = estimated_prompt_tokens
        if completion_tokens <= 0:
            completion_tokens = 0
        total_tokens = max(prompt_tokens + completion_tokens, prompt_tokens)

    return {
        "id": uuid4().hex,
        "created_at": _to_iso(datetime.now(UTC)),
        "chain_id": chain.id,
        "chain_name": chain.name,
        "version_no": version.version_no,
        "actor_username": current_user.username,
        "full_prompt": version.content,
        "prompt_with_rag": prompt_with_rag,
        "fixed_part": breakdown["fixed_part"],
        "semi_fixed_part": breakdown["semi_fixed_part"],
        "variable_part": breakdown["variable_part"],
        "variables": breakdown["variables"],
        "reliability": float(metrics["reliability"]),
        "cache_hit_probability": float(metrics["cache_hit_probability"]),
        "latency_ms": elapsed_ms,
        "llm": live.get("llm", {}),
        "llm_error": str(live.get("llm_error", "") or ""),
        "llm_response": str(live.get("response_text", "") or ""),
        "rag": rag_info,
        "security": security,
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }


def _get_filtered_test_runs(
    *,
    chain_id: int | None = None,
    version_no: int | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    with _PROMPT_TEST_RUNS_LOCK:
        snapshot = list(_PROMPT_TEST_RUNS)

    rows: list[dict[str, object]] = []
    for run in reversed(snapshot):
        if chain_id is not None and int(run.get("chain_id", 0)) != chain_id:
            continue
        if version_no is not None and int(run.get("version_no", 0)) != version_no:
            continue
        rows.append(run)
        if len(rows) >= limit:
            break
    return rows


def _write_prompt_orchestrator_log(chain_id: int, version_no: int, log_text: str) -> Path:
    log_dir = PROMPT_ORCHESTRATOR_LOG_ROOT / f"chain_{chain_id}" / f"version_{version_no}"
    log_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    log_path = log_dir / f"preview_{generated_at}.log"
    log_path.write_text(log_text, encoding="utf-8")
    latest_path = log_dir / "latest.log"
    latest_path.write_text(log_text, encoding="utf-8")
    return log_path


def _compose_prompt_orchestrator_preview(chain, version, current_user: User) -> PromptOrchestratorPreviewOut:  # type: ignore[no-untyped-def]
    prompt_with_rag, rag_info = _build_prompt_with_rag(version.content)
    metrics = crud.analyze_prompt_text(prompt_with_rag)
    security = crud.compute_prompt_security_metrics(prompt_with_rag)
    analysis = PromptVersionAnalysisOut(
        chain_id=chain.id,
        chain_name=chain.name,
        version_no=version.version_no,
        tokens=metrics["tokens"],
        reliability=metrics["reliability"],
        cache_hit_probability=metrics["cache_hit_probability"],
        injection_risk=security["injection_risk"],
        contradiction_risk=security["contradiction_risk"],
        ambiguity_risk=security["ambiguity_risk"],
        security_markers=security["markers"],
    )

    recommendations: list[str] = []
    if analysis.injection_risk >= 20:
        recommendations.append("Harden instruction hierarchy and remove conflicting directives.")
    if analysis.contradiction_risk >= 10:
        recommendations.append("Resolve contradictory constraints and make precedence explicit.")
    if analysis.ambiguity_risk >= 10:
        recommendations.append("Replace vague phrasing with concrete thresholds and expected outputs.")
    if not recommendations:
        recommendations.append("Prompt is stable; preserve structure and trim redundant text.")

    retrieved_context = rag_info.get("chunks", []) if isinstance(rag_info, dict) else []
    source_prompt = version.content.strip()
    heuristic_improved_prompt = "\n".join([
        f"You are a prompt orchestration assistant for chain '{chain.name}'.",
        "Use the retrieved context only when it is relevant to the user request.",
        "Keep the instruction hierarchy explicit: system > task > constraints > examples > retrieved context.",
        "Return a concise answer with clear sections and no unsupported claims.",
        "",
        "Source prompt:",
        source_prompt,
        "",
        "Suggested improvements:",
        "- " + "\n- ".join(recommendations),
    ])

    optimizer_prompt = "\n".join([
        "You are a prompt optimizer.",
        "Rewrite the source prompt into a stronger, safer, and clearer instruction set.",
        "Preserve user intent, placeholders, and explicit output constraints.",
        "Return only the rewritten prompt text.",
        "",
        "Source prompt:",
        source_prompt,
        "",
        "Suggested improvements:",
        "- " + "\n- ".join(recommendations),
    ])
    optimizer_live = _invoke_profiled_llm(optimizer_prompt, profile="optimizer")
    optimizer_llm = optimizer_live.get("llm", {}) if isinstance(optimizer_live, dict) else {}
    optimizer_invoked = bool(optimizer_llm.get("llm_invoked")) if isinstance(optimizer_llm, dict) else False
    optimizer_error = str(optimizer_live.get("llm_error", "") or "")
    optimized_prompt = str(optimizer_live.get("response_text", "") or "").strip() or heuristic_improved_prompt

    compression_prompt = "\n".join([
        "You are a prompt compression assistant.",
        "Compress the prompt while preserving constraints, safety rules, and placeholders.",
        "Return only the compressed prompt text.",
        "",
        "Prompt to compress:",
        optimized_prompt,
    ])
    compression_live = _invoke_profiled_llm(compression_prompt, profile="compression")
    compression_llm = compression_live.get("llm", {}) if isinstance(compression_live, dict) else {}
    compression_invoked = bool(compression_llm.get("llm_invoked")) if isinstance(compression_llm, dict) else False
    compression_error = str(compression_live.get("llm_error", "") or "")
    compressed_prompt = str(compression_live.get("response_text", "") or "").strip()

    improved_prompt = compressed_prompt or optimized_prompt

    recommendations.append(
        "Optimizer mode: "
        + ("live LLM" if optimizer_invoked else f"fallback ({optimizer_error or 'no response'})")
    )
    recommendations.append(
        "Compression mode: "
        + ("live LLM" if compression_invoked else f"fallback ({compression_error or 'no response'})")
    )

    generated_at = datetime.now(UTC).isoformat()
    log_lines = [
        "PromptMan Orchestrator Preview Log",
        f"Generated at (UTC): {generated_at}",
        f"Requested by: {current_user.username}",
        f"Chain ID: {chain.id}",
        f"Chain Name: {chain.name}",
        f"Version No: {version.version_no}",
        "",
        "Source prompt:",
        source_prompt,
        "",
        "Retrieved context:",
        *(retrieved_context or ["(none)"]),
        "",
        "Analysis JSON:",
        json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
        "",
        "Optimizer LLM snapshot:",
        json.dumps(optimizer_llm, ensure_ascii=False, indent=2) if isinstance(optimizer_llm, dict) else "{}",
        f"Optimizer error: {optimizer_error or '(none)'}",
        "",
        "Compression LLM snapshot:",
        json.dumps(compression_llm, ensure_ascii=False, indent=2) if isinstance(compression_llm, dict) else "{}",
        f"Compression error: {compression_error or '(none)'}",
        "",
        "Recommendations:",
        *(f"- {item}" for item in recommendations),
        "",
        "Improved prompt:",
        improved_prompt,
    ]
    log_text = "\n".join(log_lines).rstrip() + "\n"
    log_path = _write_prompt_orchestrator_log(chain.id, version.version_no, log_text)

    return PromptOrchestratorPreviewOut(
        chain_id=chain.id,
        chain_name=chain.name,
        version_no=version.version_no,
        source_prompt=source_prompt,
        retrieved_context=list(retrieved_context),
        analysis=analysis,
        recommendations=recommendations,
        improved_prompt=improved_prompt,
        generated_at=generated_at,
        log_path=str(log_path),
        log_text=log_text,
    )


def _chain_out(db: Session, row) -> PromptChainOut:  # type: ignore[no-untyped-def]
    created_by = run_db_call(db, crud.resolve_audit_username, row.created_by_ref)
    updated_by = run_db_call(db, crud.resolve_audit_username, row.updated_by_ref)
    return PromptChainOut(
        id=row.id,
        project=row.project_ref.name,
        name=row.name,
        description=row.description,
        created_at=_to_iso(row.created_at),
        updated_at=_to_iso(row.updated_at),
        created_by_username=created_by,
        updated_by_username=updated_by,
    )


def _version_out(db: Session, row) -> PromptChainVersionOut:  # type: ignore[no-untyped-def]
    created_by = run_db_call(db, crud.resolve_audit_username, row.created_by_ref)
    return PromptChainVersionOut(
        id=row.id,
        chain_id=row.chain_id,
        version_no=row.version_no,
        content=row.content,
        notes=row.notes,
        created_at=_to_iso(row.created_at),
        created_by_username=created_by,
    )


@router.post("/chains", response_model=PromptChainOut)
def create_chain(
    payload: PromptChainCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> PromptChainOut:
    auth_service.ensure_project_access(current_user, payload.project)
    try:
        chain = run_db_call(
            db,
            crud.create_prompt_chain,
            project=payload.project,
            name=payload.name,
            description=payload.description,
            initial_content=payload.content,
            notes=payload.notes,
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _chain_out(db, chain)


@router.get("/chains", response_model=list[PromptChainOut])
def list_chains(
    project: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptChainOut]:
    rows = run_db_call(
        db,
        crud.list_prompt_chains,
        project=project,
        allowed_projects=_allowed_projects(current_user),
        limit=limit,
        offset=offset,
    )
    return [_chain_out(db, row) for row in rows]


@router.get("/chains/{chain_id}", response_model=PromptChainOut)
def get_chain(
    chain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PromptChainOut:
    row = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not row:
        raise HTTPException(status_code=404, detail="Prompt chain not found")
    return _chain_out(db, row)


@router.get("/chains/{chain_id}/versions", response_model=list[PromptChainVersionOut])
def list_chain_versions(
    chain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptChainVersionOut]:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")
    rows = run_db_call(db, crud.list_prompt_chain_versions, chain_id)
    return [_version_out(db, row) for row in rows]


@router.get("/chains/{chain_id}/versions/{version_no}", response_model=PromptChainVersionOut)
def get_chain_version(
    chain_id: int,
    version_no: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PromptChainVersionOut:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")
    row = run_db_call(db, crud.get_prompt_chain_version, chain_id, version_no)
    if not row:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return _version_out(db, row)


@router.post("/chains/{chain_id}/versions", response_model=PromptChainVersionOut)
def create_chain_version(
    chain_id: int,
    payload: PromptChainVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> PromptChainVersionOut:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")
    auth_service.ensure_project_access(current_user, chain.project_ref.name)

    row = run_db_call(
        db,
        crud.add_prompt_chain_version,
        chain=chain,
        content=payload.content,
        notes=payload.notes,
        actor_id=current_user.id,
    )
    return _version_out(db, row)


@router.post("/chains/{chain_id}/analyze", response_model=PromptChainAnalysisOut)
def analyze_chain(
    chain_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PromptChainAnalysisOut:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")

    versions = run_db_call(db, crud.list_prompt_chain_versions, chain_id)
    report = crud.build_chain_analysis_report(versions)
    return PromptChainAnalysisOut(
        chain_id=chain.id,
        chain_name=chain.name,
        summary=report["summary"],
        points=report["points"],
    )


@router.post("/chains/{chain_id}/versions/{version_no}/analyze", response_model=PromptVersionAnalysisOut)
def analyze_chain_version(
    chain_id: int,
    version_no: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PromptVersionAnalysisOut:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")

    row = run_db_call(db, crud.get_prompt_chain_version, chain_id, version_no)
    if not row:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    metrics = crud.analyze_prompt_text(row.content)
    security = crud.compute_prompt_security_metrics(row.content)
    return PromptVersionAnalysisOut(
        chain_id=chain.id,
        chain_name=chain.name,
        version_no=row.version_no,
        tokens=metrics["tokens"],
        reliability=metrics["reliability"],
        cache_hit_probability=metrics["cache_hit_probability"],
        injection_risk=security["injection_risk"],
        contradiction_risk=security["contradiction_risk"],
        ambiguity_risk=security["ambiguity_risk"],
        security_markers=security["markers"],
    )


@router.post("/chains/{chain_id}/versions/{version_no}/orchestrate", response_model=PromptOrchestratorPreviewOut)
def preview_orchestrated_prompt(
    chain_id: int,
    version_no: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PromptOrchestratorPreviewOut:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")

    row = run_db_call(db, crud.get_prompt_chain_version, chain_id, version_no)
    if not row:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    return _compose_prompt_orchestrator_preview(chain, row, current_user)


@router.post("/chains/{chain_id}/versions/{version_no}/test-runs", response_model=PromptTestRunOut)
def run_prompt_version_test(
    chain_id: int,
    version_no: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PromptTestRunOut:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")

    version = run_db_call(db, crud.get_prompt_chain_version, chain_id, version_no)
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    run = _build_prompt_test_run(chain, version, current_user)
    with _PROMPT_TEST_RUNS_LOCK:
        _PROMPT_TEST_RUNS.append(run)
    return PromptTestRunOut(**run)


@router.get("/chains/{chain_id}/versions/{version_no}/test-runs", response_model=list[PromptTestRunOut])
def list_prompt_version_test_runs(
    chain_id: int,
    version_no: int,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptTestRunOut]:
    chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
    if not chain:
        raise HTTPException(status_code=404, detail="Prompt chain not found")
    rows = _get_filtered_test_runs(chain_id=chain_id, version_no=version_no, limit=limit)
    return [PromptTestRunOut(**row) for row in rows]


@router.get("/test-runs", response_model=list[PromptTestRunOut])
def list_recent_prompt_test_runs(
    chain_id: int | None = Query(None),
    version_no: int | None = Query(None),
    limit: int = Query(50, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptTestRunOut]:
    if chain_id is not None:
        chain = run_db_call(db, crud.get_prompt_chain_by_id, chain_id, allowed_projects=_allowed_projects(current_user))
        if not chain:
            raise HTTPException(status_code=404, detail="Prompt chain not found")
    rows = _get_filtered_test_runs(chain_id=chain_id, version_no=version_no, limit=limit)
    return [PromptTestRunOut(**row) for row in rows]
