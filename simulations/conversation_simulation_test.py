from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_demo_data import seed_demo_data  # noqa: E402

LOG_PATH = Path(__file__).resolve().parent / "conversation_simulation_test.log"


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("promptman.simulation")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def _api(session: requests.Session, method: str, url: str, *, token: str | None = None, payload: Any = None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = session.request(method, url, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    if response.status_code == 204:
        return None
    return response.json()


def _safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _run_cycle(
    logger: logging.Logger,
    session: requests.Session,
    base_url: str,
    token: str,
    chain_id: int,
    version_no: int,
    cycle_no: int,
) -> dict[str, Any]:
    test_run = _api(
        session,
        "POST",
        f"{base_url}/v1/prompt-versions/chains/{chain_id}/versions/{version_no}/test-runs",
        token=token,
    )
    version_analysis = _api(
        session,
        "POST",
        f"{base_url}/v1/prompt-versions/chains/{chain_id}/versions/{version_no}/analyze",
        token=token,
    )

    logger.info("========== CYCLE %s =========", cycle_no)
    logger.info("RUN_ID: %s", test_run.get("id"))
    logger.info("CHAIN: %s VERSION: %s", test_run.get("chain_name"), test_run.get("version_no"))
    logger.info("LLM: %s", _safe(test_run.get("llm", {})))
    logger.info("LLM_ERROR: %s", test_run.get("llm_error", ""))
    logger.info("TOKEN_USAGE: %s", _safe(test_run.get("token_usage", {})))
    logger.info("SECURITY: %s", _safe(test_run.get("security", {})))
    logger.info("RAG: %s", _safe(test_run.get("rag", {})))

    logger.info("FULL_PROMPT:\n%s", test_run.get("full_prompt", ""))
    logger.info("PROMPT_WITH_RAG:\n%s", test_run.get("prompt_with_rag", ""))
    logger.info("FIXED_PART:\n%s", test_run.get("fixed_part", ""))
    logger.info("SEMI_FIXED_PART:\n%s", test_run.get("semi_fixed_part", ""))
    logger.info("VARIABLE_PART:\n%s", test_run.get("variable_part", ""))

    logger.info("LLM_RESPONSE:\n%s", test_run.get("llm_response", ""))
    logger.info("VERSION_ANALYSIS: %s", _safe(version_analysis))

    return {
        "run": test_run,
        "analysis": version_analysis,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PromptMan conversation simulation test runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="demo_admin")
    parser.add_argument("--password", default="demo_admin_2026")
    parser.add_argument("--chain-id", type=int, default=51)
    parser.add_argument("--version-no", type=int, default=5)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--seed", action="store_true", help="Seed demo data before simulation")
    parser.add_argument("--reset-db", action="store_true", help="Delete existing DB data before seeding")
    parser.add_argument("--scale", choices=["small", "medium", "large"], default="small")
    args = parser.parse_args()

    logger = _setup_logger()
    logger.info("Simulation started")
    logger.info("Command args: %s", vars(args))

    if args.seed:
        stats = seed_demo_data(scale=args.scale, reset_db=args.reset_db)
        logger.info("SEED_STATS: %s", _safe(stats))

    session = requests.Session()
    session.trust_env = False

    auth_payload = _api(
        session,
        "POST",
        f"{args.base_url.rstrip('/')}/v1/auth/login",
        payload={"username": args.username, "password": args.password},
    )
    token = auth_payload.get("access_token", "")
    if not token:
        raise RuntimeError("Authentication succeeded but access token is empty")

    results: list[dict[str, Any]] = []
    for cycle in range(1, max(1, args.cycles) + 1):
        results.append(
            _run_cycle(
                logger,
                session,
                args.base_url.rstrip("/"),
                token,
                args.chain_id,
                args.version_no,
                cycle,
            )
        )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cycles": len(results),
        "chain_id": args.chain_id,
        "version_no": args.version_no,
        "log_path": str(LOG_PATH),
        "run_ids": [item["run"].get("id") for item in results],
        "llm_invoked_count": sum(1 for item in results if item["run"].get("llm", {}).get("llm_invoked")),
        "avg_injection_risk": round(
            sum(float(item["run"].get("security", {}).get("injection_risk", 0.0)) for item in results)
            / max(1, len(results)),
            2,
        ),
        "avg_contradiction_risk": round(
            sum(float(item["run"].get("security", {}).get("contradiction_risk", 0.0)) for item in results)
            / max(1, len(results)),
            2,
        ),
    }

    logger.info("SUMMARY: %s", _safe(summary))
    print("Simulation finished")
    print(f"Log file: {LOG_PATH}")


if __name__ == "__main__":
    main()
