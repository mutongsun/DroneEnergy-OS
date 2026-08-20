"""可观测性中间件：trace_id 注入 + HTTP 指标采集"""

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.monitoring.logging import trace_id_var
from app.monitoring.metrics import HTTP_REQUEST_LATENCY, HTTP_REQUESTS_TOTAL

# 不计入业务指标的路径（抓取端点/文档），避免监控流量污染真实指标
_EXCLUDED_PREFIXES = ("/metrics", "/docs", "/openapi.json")

# BaseHTTPMiddleware 的 call_next 签名
_CallNext = Callable[[Request], Awaitable[Response]]


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 trace_id 并注入 ContextVar 与响应头"""

    async def dispatch(self, request: Request, call_next: _CallNext) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
        token = trace_id_var.set(trace_id)
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            trace_id_var.reset(token)


class MetricsMiddleware(BaseHTTPMiddleware):
    """HTTP 请求计数与耗时分布"""

    async def dispatch(self, request: Request, call_next: _CallNext) -> Response:
        if request.url.path.startswith(_EXCLUDED_PREFIXES):
            return await call_next(request)

        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            # 路由匹配发生在 call_next 内部，此时 scope 已带 route；
            # 用「路由模板」做标签（如 /flights/{id}），
            # 避免 /flights/1、/flights/2 造成标签基数爆炸
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            HTTP_REQUESTS_TOTAL.labels(request.method, path, str(status)).inc()
            HTTP_REQUEST_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
