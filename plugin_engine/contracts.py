from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


PluginName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")]
EndpointName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")]


class PluginUiOption(BaseModel):
    label: str
    value: str


class PluginEndpointConfig(BaseModel):
    name: EndpointName
    description: str = ""
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    roles: list[str] = Field(default_factory=lambda: ["admin"])
    timeout_seconds: int = 30
    include_in_schema: bool = True
    launches_modal: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith("_"):
            raise ValueError("Plugin endpoint names must not start with '_'")
        if normalized == "health":
            raise ValueError("Plugin endpoint name 'health' is reserved")
        if normalized.endswith("_init"):
            raise ValueError("Plugin endpoint names must not end with '_init'")
        return normalized


class PluginUiControl(BaseModel):
    name: EndpointName
    control_type: Literal["button", "dropdown", "checkbox", "text", "textarea"]
    label: str
    endpoint_name: EndpointName
    init_endpoint_name: str | None = None
    description: str = ""
    placeholder: str | None = None
    options: list[PluginUiOption] = Field(default_factory=list)
    default_value: Any = None
    trigger: Literal["click", "change", "manual"] = "change"

    @field_validator("init_endpoint_name")
    @classmethod
    def normalize_init_endpoint_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


class PluginHookConfig(BaseModel):
    target_method: Literal["GET", "POST", "PUT", "DELETE"]
    target_path: str
    before_endpoint: str | None = None
    after_endpoint: str | None = None
    failure_limit: int = 3


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PluginName
    version: str
    description: str
    icon: str | None = None
    min_promptman_version: str = "0.0.0"
    max_promptman_version: str | None = None
    lifecycle_timeout_seconds: int = 30
    health_timeout_seconds: int = 10
    runtime_failure_limit: int = 3
    endpoints: list[PluginEndpointConfig] = Field(default_factory=list)
    ui_controls: list[PluginUiControl] = Field(default_factory=list)
    hooks: list[PluginHookConfig] = Field(default_factory=list)

    @field_validator("endpoints")
    @classmethod
    def ensure_unique_endpoints(cls, value: list[PluginEndpointConfig]) -> list[PluginEndpointConfig]:
        seen: set[str] = set()
        for item in value:
            if item.name in seen:
                raise ValueError(f"Duplicate plugin endpoint '{item.name}'")
            seen.add(item.name)
        return value


class PluginActionResult(BaseModel):
    message: str
    plugin_name: str | None = None
    state: str | None = None


class PluginCatalogEntry(BaseModel):
    name: str
    version: str = "unknown"
    description: str = ""
    icon: str | None = None
    source_path: str
    state: str
    compatible: bool = True
    available: bool = False
    min_promptman_version: str = "0.0.0"
    max_promptman_version: str | None = None
    last_error: str | None = None
    unavailable_reason: str | None = None
    health_failures: int = 0
    signature_status: str = "unsigned"
    signature_signer: str | None = None
    signature_error: str | None = None
    runtime_failures: dict[str, int] = Field(default_factory=dict)
    endpoints: list[PluginEndpointConfig] = Field(default_factory=list)
    ui_controls: list[PluginUiControl] = Field(default_factory=list)
    hooks: list[PluginHookConfig] = Field(default_factory=list)
    init_results: dict[str, Any] = Field(default_factory=dict)
    active_routes: list[str] = Field(default_factory=list)


class PluginSignatureEnvelope(BaseModel):
    signer_id: str
    algorithm: Literal["ed25519"] = "ed25519"
    file: str
    signature: str


class PluginSignerRecord(BaseModel):
    signer_id: str
    algorithm: Literal["ed25519"] = "ed25519"
    public_key: str


class PluginEndpointDiagnosticEntry(BaseModel):
    endpoint_name: str
    consecutive_failures: int = 0
    blocked: bool = False
    last_error: str | None = None


class PluginHookDiagnosticEntry(BaseModel):
    hook_key: str
    consecutive_failures: int = 0
    blocked: bool = False
    last_error: str | None = None


class PluginDiagnosticsOut(BaseModel):
    plugin_name: str
    state: str
    available: bool = False
    lifecycle_active: bool = False
    health_failures: int = 0
    signature_status: str = "unsigned"
    signature_signer: str | None = None
    signature_error: str | None = None
    unavailable_reason: str | None = None
    endpoint_diagnostics: list[PluginEndpointDiagnosticEntry] = Field(default_factory=list)
    hook_diagnostics: list[PluginHookDiagnosticEntry] = Field(default_factory=list)


class PluginModalChartPoint(BaseModel):
    label: str
    value: float


class PluginModalChartSpec(BaseModel):
    id: str
    title: str
    tooltip: str = ""
    kind: Literal["bar", "line"] = "line"
    points: list[PluginModalChartPoint] = Field(default_factory=list)
    value_min: float | None = None
    value_max: float | None = None
    y_label: str = ""


class PluginModalTabSpec(BaseModel):
    id: str
    label: str
    body_markdown: str = ""
    controls: list[PluginUiControl] = Field(default_factory=list)
    charts: list[PluginModalChartSpec] = Field(default_factory=list)


class PluginModalSpec(BaseModel):
    title: str
    description: str = ""
    body_markdown: str = ""
    controls: list[PluginUiControl] = Field(default_factory=list)
    tabs: list[PluginModalTabSpec] = Field(default_factory=list)
    active_tab: str | None = None
    allow_stop: bool = True
    stop_label: str = "Stop Plugin"
    close_label: str = "Close"
    primary_action_label: str | None = None
    status: str = ""


class PluginModalStartRequest(BaseModel):
    endpoint_name: EndpointName
    payload: Any = None
    controls: dict[str, Any] = Field(default_factory=dict)


class PluginModalControlUpdateRequest(BaseModel):
    control_name: EndpointName
    value: Any = None
    controls: dict[str, Any] = Field(default_factory=dict)


class PluginModalSessionOut(BaseModel):
    session_id: str
    plugin_name: str
    endpoint_name: str
    state: Literal["opening", "running", "stopping", "stopped", "completed", "error"]
    modal: PluginModalSpec
    control_values: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    stop_requested: bool = False
    last_result: Any = None
    last_error: str | None = None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class PluginLifecycleContext:
    app: Any
    engine: Any
    plugin_name: str
    manifest: PluginManifest
    init_results: dict[str, Any]


@dataclass(slots=True)
class PluginRequestSnapshot:
    method: str
    path: str
    route_path: str | None
    query: dict[str, Any]
    headers: dict[str, str]
    body: Any = None


@dataclass(slots=True)
class PluginRunContext:
    app: Any
    engine: Any
    plugin_name: str
    manifest: PluginManifest
    endpoint_name: str
    current_user: Any | None
    payload: Any
    request: PluginRequestSnapshot
    phase: Literal["runtime", "hook", "health", "init-endpoint", "modal"]
    hook: PluginHookConfig | None = None
    response_status_code: int | None = None
    modal_session_id: str | None = None
    modal_action: str | None = None
    modal_controls: dict[str, Any] | None = None
    modal_stop_requested: bool = False