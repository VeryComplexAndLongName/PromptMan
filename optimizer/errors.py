from __future__ import annotations


class BackendOperationTimeoutError(TimeoutError):
    def __init__(self, operation_name: str, timeout_seconds: int) -> None:
        super().__init__(f"{operation_name} exceeded {int(timeout_seconds)}s timeout")
        self.operation_name = operation_name
        self.timeout_seconds = int(timeout_seconds)
