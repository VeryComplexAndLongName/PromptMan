import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app_settings
from plugin_engine import PluginEngine, PluginModalControlUpdateRequest, PluginModalStartRequest


def _generate_signing_material(signer_id: str, output_dir: Path) -> Path:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_b64 = base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("utf-8")

    output_dir.mkdir(parents=True, exist_ok=True)
    private_key_path = output_dir / f"{signer_id}.ed25519.private.pem"
    private_key_path.write_bytes(private_pem)
    (output_dir / f"{signer_id}.trusted-signer.json").write_text(
        json.dumps(
            {
                signer_id: {
                    "algorithm": "ed25519",
                    "public_key": public_b64,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return private_key_path


def _sign_plugin_file(plugin_path: Path, signer_id: str, private_key_path: Path) -> None:
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    signature = private_key.sign(plugin_path.read_bytes())
    plugin_path.with_suffix(".signature.json").write_text(
        json.dumps(
            {
                "signer_id": signer_id,
                "algorithm": "ed25519",
                "file": plugin_path.name,
                "signature": base64.b64encode(signature).decode("utf-8"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_plugin_catalog_lists_example_plugins(client):  # type: ignore[no-untyped-def]
    response = client.get("/v1/plugins")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload}
    assert "example_ui" in names
    assert "example_headless" in names
    assert "example_modal" in names


def test_recursive_plugin_scan_discovers_nested_plugins(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    nested_dir = plugin_dir / "demos" / "workbenches"
    nested_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = nested_dir / "nested_modal.py"
    plugin_path.write_text(
        "from plugin_engine import PluginManifest\n"
        "\n"
        "def plugin_preinit():\n"
        "    return PluginManifest(name='nested_modal', version='1.0.0', description='nested', endpoints=[])\n"
        "\n"
        "def plugin_init(context):\n"
        "    return None\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    return None\n"
        "\n"
        "def plugin_run(context):\n"
        "    if context.endpoint_name == 'health':\n"
        "        return {'ok': True}\n"
        "    return {'ok': True}\n"
        "\n"
        "def plugin_done(context):\n"
        "    return None\n",
        encoding="utf-8",
    )

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine

    asyncio.run(engine.rescan(auto_activate=True))

    catalog = engine.list_plugins()
    names = {item.name for item in catalog}
    assert "nested_modal" in names
    assert engine.records["nested_modal"].source_path == plugin_path


def test_example_ui_plugin_endpoint_executes(client):  # type: ignore[no-untyped-def]
    response = client.post("/v1/plugins/example_ui/run_demo", json={"value": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "Example UI plugin executed"


def test_plugin_routes_are_registered_in_openapi(client):  # type: ignore[no-untyped-def]
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json().get("paths", {})
    assert "/v1/plugins/example_ui/run_demo" in paths
    assert "/v1/plugins/example_headless/ping" in paths
    assert "/v1/plugins/{plugin_name}/modals" in paths
    assert "/v1/plugins/{plugin_name}/modals/{session_id}/stop" in paths


def test_headless_plugin_hook_runs_fail_open(client):  # type: ignore[no-untyped-def]
    version_response = client.get("/v1/version")
    plugin_response = client.post("/v1/plugins/example_headless/ping", json={})

    assert version_response.status_code == 200
    assert plugin_response.status_code == 200
    payload = plugin_response.json()
    assert payload["before"] >= 1
    assert payload["after"] >= 1


def test_plugin_catalog_reports_verified_signature(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "signed_sample.py"
    plugin_path.write_text(
        "from plugin_engine import PluginManifest\n"
        "\n"
        "def plugin_preinit():\n"
        "    return PluginManifest(name='signed_sample', version='1.0.0', description='signed', endpoints=[])\n"
        "\n"
        "def plugin_init(context):\n"
        "    return None\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    return None\n"
        "\n"
        "def plugin_run(context):\n"
        "    return {'ok': True}\n"
        "\n"
        "def plugin_done(context):\n"
        "    return None\n",
        encoding="utf-8",
    )

    keys_dir = plugin_dir / "keys"
    private_key_path = _generate_signing_material("test-signer", keys_dir)
    trust_snippet = (keys_dir / "test-signer.trusted-signer.json").read_text(encoding="utf-8")
    (plugin_dir / "trusted_signers.json").write_text(trust_snippet, encoding="utf-8")
    _sign_plugin_file(plugin_path, "test-signer", private_key_path)

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine

    asyncio.run(engine.rescan(auto_activate=True))

    catalog = engine.list_plugins()
    assert len(catalog) == 1
    assert catalog[0].name == "signed_sample"
    assert catalog[0].signature_status == "verified"
    assert catalog[0].signature_signer == "test-signer"


def test_plugin_is_deactivated_after_three_runtime_failures(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "broken_runtime.py"
    plugin_path.write_text(
        "from plugin_engine import PluginEndpointConfig, PluginManifest\n"
        "\n"
        "def plugin_preinit():\n"
        "    return PluginManifest(\n"
        "        name='broken_runtime',\n"
        "        version='1.0.0',\n"
        "        description='broken',\n"
        "        runtime_failure_limit=3,\n"
        "        endpoints=[PluginEndpointConfig(name='boom', roles=['admin'])],\n"
        "    )\n"
        "\n"
        "def plugin_init(context):\n"
        "    return None\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    return None\n"
        "\n"
        "def plugin_run(context):\n"
        "    if context.endpoint_name == 'health':\n"
        "        return {'ok': True}\n"
        "    if context.endpoint_name == 'boom_init':\n"
        "        return {'value': None}\n"
        "    raise RuntimeError('boom')\n"
        "\n"
        "def plugin_done(context):\n"
        "    return None\n",
        encoding="utf-8",
    )

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine

    asyncio.run(engine.rescan(auto_activate=True))
    record = engine.records["broken_runtime"]
    assert record.available is True

    request = engine._synthetic_request("/v1/plugins/broken_runtime/boom", "POST")
    admin_user = SimpleNamespace(role="admin")
    for _ in range(3):
        try:
            asyncio.run(
                engine.execute_plugin_endpoint(
                    "broken_runtime",
                    "boom",
                    request=request,
                    current_user=admin_user,
                    payload={},
                )
            )
        except RuntimeError:
            pass

    assert record.available is False
    assert record.state == "unavailable"
    assert record.active_routes == []
    assert record.unavailable_reason is not None
    assert record.endpoint_states["boom"].consecutive_failures == 3


def test_signed_only_mode_rejects_unsigned_plugins(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "unsigned_sample.py"
    plugin_path.write_text(
        "from plugin_engine import PluginManifest\n"
        "\n"
        "def plugin_preinit():\n"
        "    return PluginManifest(name='unsigned_sample', version='1.0.0', description='unsigned', endpoints=[])\n"
        "\n"
        "def plugin_init(context):\n"
        "    return None\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    return None\n"
        "\n"
        "def plugin_run(context):\n"
        "    return {'ok': True}\n"
        "\n"
        "def plugin_done(context):\n"
        "    return None\n",
        encoding="utf-8",
    )

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine

    previous = app_settings.get("PROMPTMAN_PLUGINS_SIGNED_ONLY", "false")
    app_settings.apply("PROMPTMAN_PLUGINS_SIGNED_ONLY", "true")
    try:
        asyncio.run(engine.rescan(auto_activate=True))
    finally:
        app_settings.apply("PROMPTMAN_PLUGINS_SIGNED_ONLY", previous)

    catalog = engine.list_plugins()
    assert len(catalog) == 1
    assert catalog[0].name == "unsigned_sample"
    assert catalog[0].signature_status == "unsigned"
    assert "signed_only" in (catalog[0].last_error or "").lower() or "unsigned plugin" in (catalog[0].last_error or "").lower()


def test_health_check_recovers_unavailable_plugin_without_reload(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "recoverable_runtime.py"
    plugin_path.write_text(
        "from plugin_engine import PluginEndpointConfig, PluginManifest\n"
        "_STATE = {'failures': 0}\n"
        "\n"
        "def plugin_preinit():\n"
        "    return PluginManifest(\n"
        "        name='recoverable_runtime',\n"
        "        version='1.0.0',\n"
        "        description='recoverable',\n"
        "        runtime_failure_limit=3,\n"
        "        endpoints=[PluginEndpointConfig(name='boom', roles=['admin'])],\n"
        "    )\n"
        "\n"
        "def plugin_init(context):\n"
        "    return None\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    return None\n"
        "\n"
        "def plugin_run(context):\n"
        "    if context.endpoint_name == 'health':\n"
        "        return {'ok': True}\n"
        "    if context.endpoint_name == 'boom_init':\n"
        "        return {'value': None}\n"
        "    _STATE['failures'] += 1\n"
        "    if _STATE['failures'] <= 3:\n"
        "        raise RuntimeError('boom')\n"
        "    return {'ok': True, 'message': 'recovered'}\n"
        "\n"
        "def plugin_done(context):\n"
        "    return None\n",
        encoding="utf-8",
    )

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine
    asyncio.run(engine.rescan(auto_activate=True))
    record = engine.records["recoverable_runtime"]

    request = engine._synthetic_request("/v1/plugins/recoverable_runtime/boom", "POST")
    admin_user = SimpleNamespace(role="admin")
    for _ in range(3):
        try:
            asyncio.run(
                engine.execute_plugin_endpoint(
                    "recoverable_runtime",
                    "boom",
                    request=request,
                    current_user=admin_user,
                    payload={},
                )
            )
        except RuntimeError:
            pass

    assert record.state == "unavailable"
    assert record.active_routes == []

    result = asyncio.run(engine.run_health_check("recoverable_runtime"))

    assert result.state == "running"
    assert record.state == "running"
    assert record.available is True
    assert record.active_routes != []


def test_plugin_diagnostics_endpoint_returns_runtime_and_hook_state(client):  # type: ignore[no-untyped-def]
    version_response = client.get("/v1/version")
    assert version_response.status_code == 200

    diagnostics_response = client.get("/v1/plugins/example_headless/_diagnostics")

    assert diagnostics_response.status_code == 200
    payload = diagnostics_response.json()
    assert payload["plugin_name"] == "example_headless"
    assert payload["state"] in {"running", "unavailable", "stopped"}
    assert isinstance(payload["hook_diagnostics"], list)
    assert isinstance(payload["endpoint_diagnostics"], list)


def test_plugin_lifecycle_order_and_done_on_unload(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "order_probe.py"
    plugin_path.write_text(
        "from plugin_engine import PluginEndpointConfig, PluginManifest\n"
        "\n"
        "CALLS = []\n"
        "LAST_RUNTIME = {}\n"
        "\n"
        "def plugin_preinit():\n"
        "    CALLS.append('plugin_preinit')\n"
        "    return PluginManifest(\n"
        "        name='order_probe',\n"
        "        version='1.0.0',\n"
        "        description='order probe',\n"
        "        endpoints=[PluginEndpointConfig(name='main_action', roles=['admin'])],\n"
        "    )\n"
        "\n"
        "def plugin_init(context):\n"
        "    CALLS.append('plugin_init')\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    CALLS.append('plugin_postinit')\n"
        "\n"
        "def plugin_run(context):\n"
        "    CALLS.append(f'plugin_run:{context.endpoint_name}:{context.phase}')\n"
        "    LAST_RUNTIME['endpoint_name'] = context.endpoint_name\n"
        "    LAST_RUNTIME['phase'] = context.phase\n"
        "    LAST_RUNTIME['payload'] = context.payload\n"
        "    LAST_RUNTIME['method'] = context.request.method\n"
        "    LAST_RUNTIME['path'] = context.request.path\n"
        "    LAST_RUNTIME['route_path'] = context.request.route_path\n"
        "    if context.endpoint_name.endswith('_init'):\n"
        "        return {'value': 'init-ok'}\n"
        "    return {'ok': True, 'echo': context.payload}\n"
        "\n"
        "def plugin_done(context):\n"
        "    CALLS.append('plugin_done')\n",
        encoding="utf-8",
    )

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine
    asyncio.run(engine.rescan(auto_activate=True))

    record = engine.records["order_probe"]
    module = record.module
    assert module is not None

    startup_calls = list(module.CALLS)
    assert startup_calls == [
        "plugin_preinit",
        "plugin_init",
        "plugin_run:main_action_init:init-endpoint",
        "plugin_postinit",
    ]

    request = engine._synthetic_request("/v1/plugins/order_probe/main_action", "POST")
    admin_user = SimpleNamespace(role="admin")
    payload = {"value": 123, "controls": {"verbose": True}}

    runtime_result = asyncio.run(
        engine.execute_plugin_endpoint(
            "order_probe",
            "main_action",
            request=request,
            current_user=admin_user,
            payload=payload,
        )
    )

    assert runtime_result["ok"] is True
    assert runtime_result["echo"] == payload
    assert module.LAST_RUNTIME["endpoint_name"] == "main_action"
    assert module.LAST_RUNTIME["phase"] == "runtime"
    assert module.LAST_RUNTIME["payload"] == payload
    assert module.LAST_RUNTIME["method"] == "POST"
    assert module.LAST_RUNTIME["path"] == "/v1/plugins/order_probe/main_action"

    unload_result = asyncio.run(engine.unload_plugin("order_probe", remove_from_catalog=False))
    assert unload_result.state == "stopped"

    assert module.CALLS == [
        "plugin_preinit",
        "plugin_init",
        "plugin_run:main_action_init:init-endpoint",
        "plugin_postinit",
        "plugin_run:main_action:runtime",
        "plugin_done",
    ]


def test_plugin_modal_session_supports_control_updates_and_stop(tmp_path: Path):  # type: ignore[no-untyped-def]
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugin_dir / "modal_probe.py"
    plugin_path.write_text(
        "from plugin_engine import PluginEndpointConfig, PluginManifest, PluginUiControl, PluginUiOption\n"
        "\n"
        "CALLS = []\n"
        "STATE = {'text': 'seed', 'mode': 'balanced', 'verbose': False}\n"
        "LAST_CONTEXT = {}\n"
        "\n"
        "def plugin_preinit():\n"
        "    CALLS.append('plugin_preinit')\n"
        "    return PluginManifest(\n"
        "        name='modal_probe',\n"
        "        version='1.0.0',\n"
        "        description='modal probe',\n"
        "        endpoints=[\n"
        "            PluginEndpointConfig(name='open_workbench', roles=['admin'], launches_modal=True),\n"
        "            PluginEndpointConfig(name='set_text', roles=['admin']),\n"
        "            PluginEndpointConfig(name='set_mode', roles=['admin']),\n"
        "            PluginEndpointConfig(name='set_verbose', roles=['admin']),\n"
        "            PluginEndpointConfig(name='run_task', roles=['admin']),\n"
        "        ],\n"
        "    )\n"
        "\n"
        "def plugin_init(context):\n"
        "    CALLS.append('plugin_init')\n"
        "\n"
        "def plugin_postinit(context):\n"
        "    CALLS.append('plugin_postinit')\n"
        "\n"
        "def _modal_spec():\n"
        "    return {\n"
        "        'title': 'Modal Probe Workbench',\n"
        "        'description': 'Probe modal',\n"
        "        'body_markdown': 'Modal body',\n"
        "        'controls': [\n"
        "            PluginUiControl(name='text_input', control_type='text', label='Text', endpoint_name='set_text', init_endpoint_name='set_text_init', placeholder='Type text...'),\n"
        "            PluginUiControl(name='mode_selector', control_type='dropdown', label='Mode', endpoint_name='set_mode', init_endpoint_name='set_mode_init', options=[PluginUiOption(label='Balanced', value='balanced'), PluginUiOption(label='Fast', value='fast')], default_value='balanced'),\n"
        "            PluginUiControl(name='verbose_toggle', control_type='checkbox', label='Verbose', endpoint_name='set_verbose', init_endpoint_name='set_verbose_init', default_value=False),\n"
        "            PluginUiControl(name='run_button', control_type='button', label='Run Task', endpoint_name='run_task', trigger='click'),\n"
        "        ],\n"
        "        'allow_stop': True,\n"
        "        'stop_label': 'Stop Work',\n"
        "        'close_label': 'Close Work',\n"
        "        'status': 'Ready',\n"
        "    }\n"
        "\n"
        "def plugin_run(context):\n"
        "    CALLS.append(f'{context.endpoint_name}:{context.phase}:{context.modal_session_id or \"none\"}')\n"
        "    LAST_CONTEXT['endpoint_name'] = context.endpoint_name\n"
        "    LAST_CONTEXT['phase'] = context.phase\n"
        "    LAST_CONTEXT['modal_session_id'] = context.modal_session_id\n"
        "    LAST_CONTEXT['modal_stop_requested'] = context.modal_stop_requested\n"
        "    LAST_CONTEXT['payload'] = context.payload\n"
        "    if context.endpoint_name == 'open_workbench':\n"
        "        return {'ok': True, 'message': 'opened', 'modal': _modal_spec()}\n"
        "    if context.endpoint_name == 'set_text_init':\n"
        "        return {'value': STATE['text'], 'message': 'text init'}\n"
        "    if context.endpoint_name == 'set_mode_init':\n"
        "        return {'value': STATE['mode'], 'message': 'mode init'}\n"
        "    if context.endpoint_name == 'set_verbose_init':\n"
        "        return {'value': STATE['verbose'], 'message': 'verbose init'}\n"
        "    if context.endpoint_name == 'set_text':\n"
        "        STATE['text'] = str((context.payload or {}).get('value') or '')\n"
        "        return {'ok': True, 'value': STATE['text'], 'message': 'text updated', 'status': 'Text updated'}\n"
        "    if context.endpoint_name == 'set_mode':\n"
        "        STATE['mode'] = str((context.payload or {}).get('value') or 'balanced')\n"
        "        return {'ok': True, 'value': STATE['mode'], 'message': 'mode updated', 'status': 'Mode updated'}\n"
        "    if context.endpoint_name == 'set_verbose':\n"
        "        STATE['verbose'] = bool((context.payload or {}).get('value', False))\n"
        "        return {'ok': True, 'value': STATE['verbose'], 'message': 'verbose updated', 'status': 'Verbose updated'}\n"
        "    if context.endpoint_name == 'run_task':\n"
        "        if context.modal_stop_requested:\n"
        "            return {'ok': False, 'message': 'stopped', 'status': 'Stopped', 'logs': ['stop requested']}\n"
        "        return {'ok': True, 'message': 'task complete', 'status': 'Completed', 'logs': [STATE['text'], STATE['mode'], str(STATE['verbose'])]}\n"
        "    return {'ok': False, 'message': 'unknown'}\n"
        "\n"
        "def plugin_done(context):\n"
        "    CALLS.append('plugin_done')\n",
        encoding="utf-8",
    )

    app = FastAPI()
    engine = PluginEngine(app, plugins_dir=plugin_dir, app_version="1.0.0")
    app.state.plugin_engine = engine
    asyncio.run(engine.rescan(auto_activate=True))

    admin_user = SimpleNamespace(role="admin")
    start_request = PluginModalStartRequest(endpoint_name="open_workbench", payload={"source": "ui"})
    start_snapshot = engine._synthetic_request("/v1/plugins/modal_probe/modals", "POST")
    session = asyncio.run(engine.start_modal_session("modal_probe", start_snapshot, admin_user, start_request))

    record = engine.records["modal_probe"]
    module = record.module
    assert module is not None
    assert session.state == "running"
    assert session.modal.title == "Modal Probe Workbench"
    assert session.control_values["text_input"] == "seed"
    assert session.control_values["mode_selector"] == "balanced"
    assert session.control_values["verbose_toggle"] is False
    assert module.LAST_CONTEXT["endpoint_name"] == "run_task_init"
    assert module.LAST_CONTEXT["phase"] == "init-endpoint"
    assert module.LAST_CONTEXT["modal_session_id"] == session.session_id

    update_request = PluginModalControlUpdateRequest(control_name="text_input", value="hello", controls={"text_input": "hello", "mode_selector": "balanced", "verbose_toggle": False})
    update_snapshot = engine._synthetic_request(f"/v1/plugins/modal_probe/modals/{session.session_id}/controls/text_input", "PATCH")
    updated_session = asyncio.run(
        engine.update_modal_control("modal_probe", session.session_id, "text_input", update_snapshot, admin_user, update_request)
    )

    assert updated_session.control_values["text_input"] == "hello"
    assert module.LAST_CONTEXT["endpoint_name"] == "set_text"
    assert module.LAST_CONTEXT["phase"] == "modal"
    assert module.LAST_CONTEXT["modal_session_id"] == session.session_id
    assert module.LAST_CONTEXT["modal_stop_requested"] is False
    assert module.LAST_CONTEXT["payload"]["value"] == "hello"

    stopped_session = asyncio.run(engine.stop_modal_session("modal_probe", session.session_id))
    assert stopped_session.stop_requested is True
    assert stopped_session.state == "stopped"

    with pytest.raises(Exception):
        asyncio.run(
            engine.update_modal_control("modal_probe", session.session_id, "text_input", update_snapshot, admin_user, update_request)
        )

    close_result = asyncio.run(engine.close_modal_session("modal_probe", session.session_id))
    assert close_result.state == "stopped"
    assert session.session_id not in engine.modal_sessions