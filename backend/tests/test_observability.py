"""可观测性中间件测试：trace_id 注入/透传与 HTTP 指标采集"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.middleware.observability import MetricsMiddleware, TraceIdMiddleware

app = FastAPI()
# 与 main.py 相同的中间件叠放顺序（TraceId 外层）
app.add_middleware(MetricsMiddleware)
app.add_middleware(TraceIdMiddleware)


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"pong": "ok"}


client = TestClient(app)


def test_trace_id_generated_and_returned() -> None:
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.headers["X-Trace-Id"]  # 未传入时自动生成


def test_trace_id_passthrough() -> None:
    resp = client.get("/ping", headers={"X-Trace-Id": "abc123"})
    assert resp.headers["X-Trace-Id"] == "abc123"  # 沿用上游 trace_id


def test_http_metrics_recorded_with_route_template() -> None:
    def _total() -> float:
        return float(
            REGISTRY.get_sample_value(
                "http_requests_total", {"method": "GET", "route": "/ping", "status": "200"}
            )
            or 0.0
        )

    before = _total()
    client.get("/ping")
    assert _total() == before + 1
