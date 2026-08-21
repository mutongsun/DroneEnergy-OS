"""Prometheus 指标注册中心

命名遵循 Prometheus 规范：Counter 以 _total 结尾，耗时以 _seconds 结尾。
标签设计原则：只使用低基数字段（method / 路由模板 / status / drone_id），
严禁把用户 ID、URL 原始路径等高基数信息做成标签（会把时序库打爆）。
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------- HTTP ----------
HTTP_REQUESTS_TOTAL = Counter("http_requests_total", "HTTP 请求总数", ["method", "route", "status"])
HTTP_REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求耗时分布",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# ---------- WebSocket / 数据接入 ----------
WS_ACTIVE_CONNECTIONS = Gauge("ws_active_connections", "当前活跃 WebSocket 连接数")
WS_MESSAGES_SENT_TOTAL = Counter("ws_messages_sent_total", "WS 下行消息总数", ["drone_id"])
# close_code 取值：4401（令牌无效）/ 4403（角色不足）
WS_AUTH_FAILURES_TOTAL = Counter("ws_auth_failures_total", "WS 握手认证失败次数", ["close_code"])
SENSOR_FRAMES_RECEIVED_TOTAL = Counter("sensor_frames_received_total", "接收到的传感器数据帧总数")
SENSOR_FRAMES_WRITTEN_TOTAL = Counter("sensor_frames_written_total", "批量写入数据库的传感器帧总数")

# ---------- AI（DeepSeek）----------
# status 取值：ok / error / circuit_open
AI_CALLS_TOTAL = Counter("ai_calls_total", "AI 调用结果计数", ["status"])
AI_CALL_LATENCY = Histogram(
    "ai_call_duration_seconds",
    "AI 调用耗时分布",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0),
)

# ---------- 数据库 ----------
DB_POOL_IN_USE = Gauge("db_pool_in_use", "当前被借出的数据库连接数")


def instrument_engine(engine: object) -> None:
    """把 SQLAlchemy 连接池的借出/归还接入指标（创建 engine 后调用一次）"""
    from sqlalchemy import event

    @event.listens_for(engine, "checkout")
    def _on_checkout(*args: object) -> None:
        DB_POOL_IN_USE.inc()

    @event.listens_for(engine, "checkin")
    def _on_checkin(*args: object) -> None:
        DB_POOL_IN_USE.dec()
