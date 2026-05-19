from time import perf_counter

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = perf_counter()
        try:
            response: Response = await call_next(request)
            return response
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            client = request.client.host if request.client else "unknown"
            logger.exception(
                "request.exception method={} path={} query={} client={} duration_ms={:.2f}",
                request.method,
                request.url.path,
                request.url.query,
                client,
                duration_ms,
            )
            return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
