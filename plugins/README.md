# PromptMan Plugins

PromptMan loads plugins from the `plugins/` directory.
The scan is recursive, so you can organize plugins into subfolders such as `plugins/demos/` or `plugins/workbenches/`.

## Minimal contract

Each plugin is a Python module with five required functions:

```python
def plugin_preinit() -> PluginManifest: ...
def plugin_init(context: PluginLifecycleContext) -> None: ...
def plugin_postinit(context: PluginLifecycleContext) -> None: ...
def plugin_run(context: PluginRunContext): ...
def plugin_done(context: PluginLifecycleContext) -> None: ...
```

## Lifecycle

On load or app startup PromptMan runs:

1. `plugin_preinit`
2. `plugin_init`
3. `<endpoint_name>_init` for every declared endpoint
4. `plugin_postinit`

On unload or shutdown PromptMan runs:

1. `plugin_done`

On the next load the full cycle starts again.

## Simple model

- `plugin_preinit` returns a `PluginManifest`
- Each declared endpoint automatically gets two backend routes:
  - `/v1/plugins/<plugin_name>/<endpoint_name>`
  - `/v1/plugins/<plugin_name>/<endpoint_name>_init`
- Both routes are handled by `plugin_run`
- `plugin_run` receives `context.endpoint_name` so the plugin can branch on the requested action
- `health` is a reserved endpoint managed by PromptMan and also handled through `plugin_run`

## UI controls

Plugins can request UI controls in `ui_controls`.

Supported controls:

1. `button`
2. `dropdown`
3. `checkbox`
4. `text`
5. `textarea`

Controls are rendered in the same order they appear in `ui_controls`.

## Modal sessions

Plugins can open a modal workbench by returning a modal specification from `plugin_run`.

Recommended pattern:

1. Mark the entrypoint endpoint with `launches_modal=True` in `PluginEndpointConfig`
2. Call that endpoint through PromptMan or REST
3. Return a response with a `modal` object

Example response shape:

```python
{
  "ok": True,
  "message": "opened",
  "modal": {
    "title": "Modal Workbench",
    "description": "...",
    "body_markdown": "...",
    "controls": [...],
    "allow_stop": True,
    "stop_label": "Stop Plugin",
    "close_label": "Close",
  },
}
```

The modal controls use the same `PluginUiControl` contract as regular plugin UI controls.

`plugin_run` receives modal context fields:

- `phase="modal"`
- `modal_session_id`
- `modal_action`
- `modal_controls`
- `modal_stop_requested`

### REST API

PromptMan exposes modal sessions through REST endpoints:

1. `GET /v1/plugins/<plugin_name>/modals`
2. `POST /v1/plugins/<plugin_name>/modals`
3. `GET /v1/plugins/<plugin_name>/modals/<session_id>`
4. `PATCH /v1/plugins/<plugin_name>/modals/<session_id>/controls/<control_name>`
5. `POST /v1/plugins/<plugin_name>/modals/<session_id>/stop`
6. `DELETE /v1/plugins/<plugin_name>/modals/<session_id>`

The UI uses the same endpoints, so plugins are not tied to the browser.

## Hooks

Plugins can run before and after existing HTTP endpoints.

Example:

```python
PluginHookConfig(
    target_method="GET",
    target_path="/v1/version",
    before_endpoint="observe_before",
    after_endpoint="observe_after",
)
```

Hooks are fail-open.

- If a hook fails, the main PromptMan endpoint still continues.
- If the same hook fails 3 times in a row, PromptMan blocks that hook and logs the problem.

## Health checks

PromptMan exposes:

```text
POST /v1/plugins/<plugin_name>/health
```

If this health call fails 3 times in a row, the plugin is marked unavailable.

## Runtime failure isolation

Each plugin also has `runtime_failure_limit` in `PluginManifest`.

- Default value: `3`
- If the same runtime endpoint fails 3 times in a row, PromptMan deactivates the plugin
- Deactivated plugins stay visible in the catalog and in the Plugins tab, but their dynamic routes are removed until the plugin is loaded or reloaded again

Example:

```python
PluginManifest(
    name="my_plugin",
    version="1.0.0",
    description="...",
    runtime_failure_limit=3,
    endpoints=[...],
)
```

## Detached signatures

PromptMan supports optional detached signatures for plugin files.

Files:

1. `plugins/<plugin_name>.py`
2. `plugins/<plugin_name>.signature.json`
3. `plugins/trusted_signers.json`

If a plugin has no signature sidecar, it is treated as `unsigned` and can still be loaded.

If a signature sidecar exists, PromptMan verifies it before importing the plugin file.

If verification fails, the plugin is rejected.

### Trusted signer store

`plugins/trusted_signers.json` is a JSON object keyed by `signer_id`.

Example:

```json
{
  "team-a": {
    "algorithm": "ed25519",
    "public_key": "BASE64_RAW_PUBLIC_KEY"
  }
}
```

### Signature sidecar

Example `plugins/my_plugin.signature.json`:

```json
{
  "signer_id": "team-a",
  "algorithm": "ed25519",
  "file": "my_plugin.py",
  "signature": "BASE64_SIGNATURE"
}
```

### Signing workflow

PromptMan verifies detached signatures but does not generate them locally anymore.

Generate signatures outside PromptMan, for example with the dedicated PromptManSign service, and then place only these artifacts into `plugins/`:

1. the plugin file
2. the detached `.signature.json` sidecar
3. the trusted signer public key entry in `trusted_signers.json`

Do not store signing private keys inside the PromptMan repository or deployment.

### Simple file-based signing helper

PromptMan includes a transport helper for calling PromptManSign without embedding full file text into JSON.

Use:

```text
python plugins/sign_via_service.py plugins/my_plugin.py --service-url https://verycomplexandlongname.pythonanywhere.com --username <login> --password <password> --signer-id promptman-team
```

What it does:

1. Calls `POST /v1/promptman/init` with login and password
2. Reads `access_token` and window token from response
3. Uploads plugin file as `multipart/form-data` to `POST /v1/promptman/sign`
4. Writes `plugins/my_plugin.signature.json`

Optional trusted signer merge:

```text
python plugins/sign_via_service.py plugins/my_plugin.py --service-url https://verycomplexandlongname.pythonanywhere.com --username <login> --password <password> --trusted-signer-json /path/to/promptman-team.trusted-signer.json
```

With `--trusted-signer-json`, the helper also merges signer record into `plugins/trusted_signers.json`.

Quick reference with only two commands: `plugins/SIGNING_QUICKSTART.md`.

## Role-based access

Each plugin endpoint declares allowed roles in `PluginEndpointConfig.roles`.

Example:

```python
PluginEndpointConfig(name="run_demo", roles=["admin", "developer"])
```

## Hot management endpoints

Admin users can manage plugins without restarting the app:

1. `GET /v1/plugins`
2. `POST /v1/plugins/_rescan`
3. `POST /v1/plugins/<plugin_name>/_load`
4. `POST /v1/plugins/<plugin_name>/_reload`
5. `DELETE /v1/plugins/<plugin_name>`
6. `POST /v1/plugins/<plugin_name>/health`
7. `GET /v1/plugins/<plugin_name>/modals`
8. `POST /v1/plugins/<plugin_name>/modals`
9. `GET /v1/plugins/<plugin_name>/modals/<session_id>`
10. `PATCH /v1/plugins/<plugin_name>/modals/<session_id>/controls/<control_name>`
11. `POST /v1/plugins/<plugin_name>/modals/<session_id>/stop`
12. `DELETE /v1/plugins/<plugin_name>/modals/<session_id>`

## Notes for plugin authors

- Keep plugin state inside the module or in your own storage
- PromptMan does not persist plugin UI values for you
- If your plugin needs cleanup or state flush, do it inside `plugin_done`
- Keep `plugin_run` fast when possible and use your own async/background strategy for long work
- If your plugin opens a modal, make the modal entrypoint idempotent and keep follow-up control handlers short
- Respect the timeout values configured in the manifest
- If you sign plugins, keep the private key outside the repository
- If your runtime endpoint may fail transiently, handle retries inside the plugin before raising, otherwise PromptMan may deactivate the plugin after repeated failures

See:

1. `plugins/example_ui_plugin.py`
2. `plugins/example_headless_plugin.py`
3. PromptManSign external signing service