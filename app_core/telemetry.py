from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any


TRUE_VALUES = {"1", "true", "yes", "on"}


class PromptManTelemetry:
    """Optional OpenTelemetry bridge for PromptMan with lazy imports."""

    def __init__(self) -> None:
        self._initialized = False
        self._enabled = False
        self._init_error: str | None = None

        self._tracer: Any = None
        self._meter: Any = None
        self._tracer_provider: Any = None
        self._meter_provider: Any = None
        self._log_provider: Any = None

        self._http_requests: Any = None
        self._http_errors: Any = None
        self._http_latency_ms: Any = None
        self._startup_duration_ms: Any = None

        self._otlp_logger: logging.Logger | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def initialize(self, service_name: str = "promptman") -> None:
        if self._initialized:
            return

        self._initialized = True
        enabled_raw = os.getenv("ENABLE_OTEL", "false").strip().lower()
        if enabled_raw not in TRUE_VALUES:
            return

        try:
            from opentelemetry import metrics, trace
            from opentelemetry._logs import set_logger_provider
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except Exception as exc:  # pragma: no cover - optional dependency path
            self._init_error = str(exc)
            return

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        namespace = os.getenv("OTEL_SERVICE_NAMESPACE", "prompt-stack")
        environment = os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "dev")
        version = os.getenv("OTEL_SERVICE_VERSION", "unknown")

        resource = Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", service_name),
                "service.namespace": namespace,
                "service.version": version,
                "deployment.environment": environment,
            }
        )

        self._tracer_provider = TracerProvider(resource=resource)
        self._tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(self._tracer_provider)
        self._tracer = trace.get_tracer("promptman")

        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint))
        self._meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(self._meter_provider)
        self._meter = metrics.get_meter("promptman")

        self._http_requests = self._meter.create_counter("promptman_http_requests_total")
        self._http_errors = self._meter.create_counter("promptman_http_errors_total")
        self._http_latency_ms = self._meter.create_histogram("promptman_http_latency_ms", unit="ms")
        self._startup_duration_ms = self._meter.create_histogram("promptman_lifecycle_duration_ms", unit="ms")

        self._log_provider = LoggerProvider(resource=resource)
        self._log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint)))
        set_logger_provider(self._log_provider)

        self._otlp_logger = logging.getLogger("promptman.otel")
        self._otlp_logger.setLevel(logging.INFO)
        self._otlp_logger.propagate = False
        self._otlp_logger.handlers.clear()
        self._otlp_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=self._log_provider))

        self._enabled = True

    def shutdown(self) -> None:
        if not self._initialized:
            return

        if self._meter_provider is not None:
            try:
                self._meter_provider.shutdown()
            except Exception:
                pass

        if self._tracer_provider is not None:
            try:
                self._tracer_provider.shutdown()
            except Exception:
                pass

        if self._log_provider is not None:
            try:
                self._log_provider.shutdown()
            except Exception:
                pass

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None):
        if not self._enabled or self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            yield span

    def record_http(self, *, path: str, method: str, status_code: int, duration_ms: float) -> None:
        if not self._enabled:
            return
        attrs = {
            "http.method": method,
            "http.route": path,
            "http.status_code": status_code,
        }
        self._http_requests.add(1, attrs)
        self._http_latency_ms.record(duration_ms, attrs)
        if status_code >= 500:
            self._http_errors.add(1, attrs)

    def record_error(self, *, operation: str, error_type: str) -> None:
        if not self._enabled:
            return
        self._http_errors.add(1, {"operation": operation, "error.type": error_type})

    def record_lifecycle(self, *, phase: str, duration_ms: float) -> None:
        if not self._enabled:
            return
        self._startup_duration_ms.record(duration_ms, {"phase": phase})

    def emit_log(self, *, level_name: str, message: str) -> None:
        if not self._enabled or self._otlp_logger is None:
            return

        level = logging.INFO
        normalized = level_name.strip().upper()
        if normalized == "DEBUG":
            level = logging.DEBUG
        elif normalized in {"WARN", "WARNING"}:
            level = logging.WARNING
        elif normalized == "ERROR":
            level = logging.ERROR
        elif normalized == "CRITICAL":
            level = logging.CRITICAL

        self._otlp_logger.log(level, message)


telemetry = PromptManTelemetry()


def init_telemetry(service_name: str = "promptman") -> None:
    telemetry.initialize(service_name=service_name)


def shutdown_telemetry() -> None:
    telemetry.shutdown()


def monotonic_ms() -> float:
    return time.perf_counter() * 1000.0
