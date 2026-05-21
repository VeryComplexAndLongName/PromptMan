from __future__ import annotations

import os
import random
import string
from threading import Lock

from locust import HttpUser, between, task

PROJECT = os.getenv("LOADTEST_PROJECT", "loadtest")
TAGS = ["load", "perf", "prompt"]
SCENARIO = os.getenv("LOADTEST_SCENARIO", "mixed").strip().lower() or "mixed"
LOADTEST_USERNAME = os.getenv("LOADTEST_USERNAME", "admin")
LOADTEST_PASSWORD = os.getenv("LOADTEST_PASSWORD", "admin")
LOADTEST_AUTH_TOKEN = os.getenv("LOADTEST_AUTH_TOKEN", "").strip()
HOT_PROMPT_COUNT = max(5, int(os.getenv("LOADTEST_HOT_PROMPT_COUNT", "12")))

_seed_lock = Lock()
_seeded = False


def _rand_suffix(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _random_prompt_payload(unique_id: str) -> dict[str, str | None | list[str]]:
    task_value = f"rewrite_prompt_{unique_id}"
    return {
        "name": f"prompt_{unique_id}",
        "project": PROJECT,
        "tags": TAGS,
        "role": "assistant",
        "task": task_value,
        "context": "customer support",
        "constraints": "be concise",
        "output_format": "markdown",
        "examples": "n/a",
    }


def _hot_prompt_name(index: int) -> str:
    return f"prompt_hot_{index:02d}"


def _hot_prompt_payload(index: int) -> dict[str, str | None | list[str]]:
    return {
        "name": _hot_prompt_name(index),
        "project": PROJECT,
        "tags": ["load", "perf", "cache"],
        "role": "assistant",
        "task": f"summarize incident report #{index}",
        "context": "shared cache benchmark prompt",
        "constraints": "respond in bullet points",
        "output_format": "markdown",
        "examples": "n/a",
    }


def _optimization_config_payload() -> dict[str, str | int | None]:
    return {
        "llm_provider": os.getenv("LOADTEST_LLM_PROVIDER", "ollama"),
        "llm_model": os.getenv("LOADTEST_LLM_MODEL", "qwen2.5:0.5b"),
        "llm_base_url": os.getenv("LOADTEST_LLM_BASE_URL", "http://127.0.0.1:11434"),
        "llm_timeout_seconds": int(os.getenv("LOADTEST_LLM_TIMEOUT_SECONDS", "300")),
        "llm_api_token": os.getenv("LOADTEST_LLM_API_TOKEN") or None,
    }


def _cached_optimize_payload() -> dict[str, str]:
    return {
        "role": "assistant",
        "task": "Rewrite the support prompt for clarity, structure, and predictable output.",
        "context": "Shared cache load-test scenario",
        "constraints": "Keep it under 120 words and preserve markdown headings",
        "output_format": "markdown",
        "examples": "none",
    }


def _cold_optimize_payload() -> dict[str, str]:
    unique_id = _rand_suffix(12)
    return {
        "role": "assistant",
        "task": f"Rewrite the support prompt for clarity, structure, and predictable output [{unique_id}]",
        "context": f"Cold cache load-test scenario {unique_id}",
        "constraints": "Keep it under 120 words and preserve markdown headings",
        "output_format": "markdown",
        "examples": "none",
    }


def _configure_client_auth(user: HttpUser) -> None:
    if LOADTEST_AUTH_TOKEN:
        user.client.headers.update({"Authorization": f"Bearer {LOADTEST_AUTH_TOKEN}"})
        return

    response = user.client.post(
        "/v1/auth/login",
        json={"username": LOADTEST_USERNAME, "password": LOADTEST_PASSWORD},
        name="POST /v1/auth/login",
    )
    if response.status_code != 200:
        raise RuntimeError(f"loadtest login failed: status={response.status_code} body={response.text[:200]}")

    payload = response.json()
    token = payload.get("access_token")
    if token:
        user.client.headers.update({"Authorization": f"Bearer {token}"})


def _ensure_seed_data(user: HttpUser) -> None:
    global _seeded

    if _seeded:
        return

    with _seed_lock:
        if _seeded:
            return

        user.client.put(
            "/v1/optimize/config",
            json=_optimization_config_payload(),
            name="PUT /v1/optimize/config",
        )

        for index in range(HOT_PROMPT_COUNT):
            with user.client.post(
                "/v1/prompts",
                json=_hot_prompt_payload(index),
                name="POST /v1/prompts [seed]",
                catch_response=True,
            ) as response:
                if response.status_code in (200, 201, 400, 409):
                    response.success()
                    continue
                response.failure(f"seed prompt failed: status={response.status_code} body={response.text[:200]}")

        _seeded = True


class AuthenticatedUser(HttpUser):
    abstract = True

    def on_start(self) -> None:
        _configure_client_auth(self)
        _ensure_seed_data(self)


class ReadOnlyUser(AuthenticatedUser):
    wait_time = between(0.05, 0.4)
    weight = 5 if SCENARIO in {"mixed", "all"} else 0

    @task(6)
    def list_prompts(self) -> None:
        self.client.get("/v1/prompts?limit=25&offset=0", name="GET /v1/prompts")

    @task(2)
    def search_by_tag(self) -> None:
        self.client.get("/v1/prompts/search?tags=load&mode=or", name="GET /v1/prompts/search")


class CrudUser(AuthenticatedUser):
    wait_time = between(0.1, 0.8)
    weight = 3 if SCENARIO in {"mixed", "all"} else 0

    @task(2)
    def create_and_update_prompt(self) -> None:
        uid = _rand_suffix(10)
        payload = _random_prompt_payload(uid)

        create_resp = self.client.post("/v1/prompts", json=payload, name="POST /v1/prompts")
        if create_resp.status_code not in (200, 201):
            return

        update_payload = {
            "role": "assistant",
            "task": f"rewrite_prompt_{uid}_v2",
            "context": "customer support",
            "constraints": "be concise and polite",
            "output_format": "markdown",
            "examples": "n/a",
            "tags": ["load", "perf", "updated"],
        }
        self.client.put(
            f"/v1/prompts/{PROJECT}/prompt_{uid}",
            json=update_payload,
            name="PUT /v1/prompts/{project}/{name}",
        )

    @task(2)
    def read_prompt(self) -> None:
        # Reads are expected to dominate, even for CRUD users.
        self.client.get("/v1/prompts?limit=10&offset=0", name="GET /v1/prompts")


class OptimizeUser(AuthenticatedUser):
    wait_time = between(1.0, 3.0)
    weight = int(os.getenv("LOADTEST_OPTIMIZE_WEIGHT", "1")) if SCENARIO in {"mixed", "all"} else 0

    @task(1)
    def optimize_leo(self) -> None:
        payload = _cached_optimize_payload()
        self.client.post("/v1/optimize", json=payload, name="POST /v1/optimize", timeout=120)


class CacheReadUser(AuthenticatedUser):
    wait_time = between(0.02, 0.12)
    weight = 7 if SCENARIO in {"cache", "all"} else 0

    @task(5)
    def hot_prompt_detail(self) -> None:
        self.client.get(f"/v1/prompts/{PROJECT}/{_hot_prompt_name(0)}", name="GET /v1/prompts/{project}/{name} [hot]")

    @task(4)
    def hot_prompt_list(self) -> None:
        self.client.get(
            f"/v1/prompts?project={PROJECT}&limit=10&offset=0",
            name="GET /v1/prompts [hot]",
        )

    @task(3)
    def hot_prompt_search(self) -> None:
        self.client.get(
            f"/v1/prompts/search?tags=cache&mode=or&project={PROJECT}",
            name="GET /v1/prompts/search [hot]",
        )

    @task(2)
    def hot_versions(self) -> None:
        self.client.get(
            f"/v1/prompts/{PROJECT}/{_hot_prompt_name(0)}/versions",
            name="GET /v1/prompts/{project}/{name}/versions [hot]",
        )


class CacheOptimizeUser(AuthenticatedUser):
    wait_time = between(0.2, 0.8)
    weight = 2 if SCENARIO in {"cache", "optimize_hot", "all"} else 0

    @task(2)
    def hot_optimize(self) -> None:
        self.client.post("/v1/optimize", json=_cached_optimize_payload(), name="POST /v1/optimize [hot]", timeout=120)


class ColdOptimizeUser(AuthenticatedUser):
    wait_time = between(0.2, 0.8)
    weight = 2 if SCENARIO in {"optimize_cold", "all"} else 0

    @task(1)
    def cold_optimize(self) -> None:
        self.client.post("/v1/optimize", json=_cold_optimize_payload(), name="POST /v1/optimize [cold]", timeout=120)
