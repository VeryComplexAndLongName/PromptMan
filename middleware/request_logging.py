from time import perf_counter

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = perf_counter()
        client = request.client.host if request.client else "unknown"
        logger.info(
            "request.start method={} path={} query={} client={}",
            request.method,
            request.url.path,
            request.url.query,
            client,
        )

        response: Response = await call_next(request)

        duration_ms = (perf_counter() - start) * 1000
        logger.info(
            "request.end method={} path={} status={} duration_ms={:.2f}",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
