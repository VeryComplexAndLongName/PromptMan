from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http_ready(url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.5) as response:
                if 200 <= response.status < 500:
                    return
        except (URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.25)
    raise TimeoutError(f"Server did not become ready at {url} in {timeout_seconds}s")


def test_ui_config_tab_admin_can_update_global_config(tmp_path: Path):  # type: ignore[no-untyped-def]
    playwright_sync = pytest.importorskip("playwright.sync_api")
    sync_playwright = playwright_sync.sync_playwright

    db_path = tmp_path / "ui_config_e2e.db"
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["PROMPTMAN_KEY"] = "test-e2e-stable-key"
    env["BOOTSTRAP_ADMIN_USERNAME"] = "admin"
    env["BOOTSTRAP_ADMIN_PASSWORD"] = "admin"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_http_ready(f"{base_url}/auth/status")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(base_url, wait_until="domcontentloaded")
            page.get_by_label("Username").fill("admin")
            page.get_by_label("Password").fill("admin")
            page.get_by_role("button", name="Sign In").click()

            page.get_by_role("button", name="Config").click()
            page.get_by_text("Global Configuration (admin)").wait_for(timeout=10000)

            row = page.locator("div", has=page.locator("label", has_text="OPTIMIZER_PROVIDER")).first
            value_input = row.locator("input").first
            original_value = value_input.input_value().strip()
            next_value = "openai" if original_value != "openai" else "ollama"

            value_input.fill(next_value)
            row.get_by_role("button", name="Save").click()
            page.get_by_text("Saved OPTIMIZER_PROVIDER").wait_for(timeout=10000)

            page.get_by_role("button", name="Refresh Global Config").click()
            page.get_by_text("Global Configuration (admin)").wait_for(timeout=10000)
            refreshed_row = page.locator("div", has=page.locator("label", has_text="OPTIMIZER_PROVIDER")).first
            refreshed_value = refreshed_row.locator("input").first.input_value().strip()

            assert refreshed_value == next_value

            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
