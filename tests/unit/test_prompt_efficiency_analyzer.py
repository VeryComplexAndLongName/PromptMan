from __future__ import annotations

from prompt_efficiency_analizer.analyzer import PromptEfficiencyAnalyzer


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, object]]:
        return [
            {
                "version": 1,
                "role": "assistant",
                "task": "Summarize the request",
                "context": "",
                "constraints": "",
                "output_format": "",
                "examples": "",
            }
        ]


class _FakeSession:
    def __init__(self) -> None:
        self.trust_env = True
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float, verify: bool) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "timeout": timeout,
                "verify": verify,
            }
        )
        return _FakeResponse()


def test_promptman_versions_requests_bypass_local_proxy(monkeypatch):  # type: ignore[no-untyped-def]
    sessions: list[_FakeSession] = []

    def fake_session_factory() -> _FakeSession:
      session = _FakeSession()
      sessions.append(session)
      return session

    monkeypatch.setattr("prompt_efficiency_analizer.analyzer.requests.Session", fake_session_factory)

    analyzer = PromptEfficiencyAnalyzer()
    snapshots = analyzer._fetch_promptman_versions(
        base_url="http://127.0.0.1:8000",
        project="loadtest",
        prompt_name="efficiency_analizer_ui",
        version_selector="all",
        access_token=None,
        verify_tls=True,
    )

    assert len(sessions) == 1
    assert sessions[0].trust_env is False
    assert len(sessions[0].calls) == 1
    assert sessions[0].calls[0]["url"] == "http://127.0.0.1:8000/v1/prompts/loadtest/efficiency_analizer_ui/versions"
    assert [snapshot.label for snapshot in snapshots] == ["v1"]