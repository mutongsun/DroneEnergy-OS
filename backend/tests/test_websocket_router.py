"""WS 端点集成测试：生产者/消费者端点分离（v2 架构）+ 握手期令牌认证（v3）

TestClient 不走 lifespan，因此用替身注入 app.state.ws_manager，
验证端点对 manager 的调用契约：
- /ws/upload/{id}：上行 sensor_frame → send_sensor_frame（不注册订阅）
- /ws/realtime/{id}：注册订阅；断开时幂等清理
- 认证矩阵：无令牌 4401 / 伪令牌 4401 / viewer 上传 4403 / viewer 观看放行

拒绝类用例必须在 with 块内显式 receive：服务端 accept 后立即 close，
关闭帧只有被读取时 TestClient 才抛 WebSocketDisconnect。
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


class StubManager:
    """替身：只记录端点对 manager 的调用"""

    def __init__(self) -> None:
        self.broadcasts: list[tuple[int, dict[str, Any]]] = []
        self.connected: list[int] = []
        self.disconnected: list[int] = []

    async def connect(self, ws: Any, drone_id: int) -> None:
        await ws.accept()
        self.connected.append(drone_id)

    async def disconnect(self, ws: Any, drone_id: int) -> None:
        self.disconnected.append(drone_id)

    async def send_sensor_frame(self, drone_id: int, data: dict[str, Any]) -> None:
        self.broadcasts.append((drone_id, data))


@pytest.fixture
def ws_manager() -> StubManager:
    manager = StubManager()
    app.state.ws_manager = manager
    yield manager
    del app.state.ws_manager


def _make_user(username: str, password: str, role: str) -> None:
    """登录接口只认证不注册，先直接入库建号"""
    from app.auth.security import hash_password
    from app.models import User
    from tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        db.add(User(username=username, password_hash=hash_password(password), role=role))
        db.commit()


def _login_token(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def ws_token(client: TestClient) -> str:
    """签发一个 operator 令牌供 WS 查询参数使用"""
    _make_user("op", "op-pass-123", "operator")
    return _login_token(client, "op", "op-pass-123")


def test_upload_endpoint_broadcasts_frames(
    client: TestClient, ws_manager: StubManager, ws_token: str
) -> None:
    frame = {"type": "sensor_frame", "voltage_v": 22.1, "battery_soc_percent": 88.5}
    with client.websocket_connect(f"/ws/upload/3?token={ws_token}") as ws:
        ws.send_text(json.dumps(frame))
        ws.send_text("not-a-json")  # 非 JSON 上行：忽略且不断连
        ws.send_text(json.dumps({"type": "unknown"}))  # 未知类型：不广播

    assert ws_manager.broadcasts == [(3, frame)]
    assert ws_manager.connected == []  # 生产者不注册订阅表（无回声）


def test_realtime_endpoint_subscribes(
    client: TestClient, ws_manager: StubManager, ws_token: str
) -> None:
    with client.websocket_connect(f"/ws/realtime/5?token={ws_token}"):
        pass  # 立即关闭

    assert ws_manager.connected == [5]
    assert ws_manager.disconnected == [5]  # finally 兜底清理
    assert ws_manager.broadcasts == []  # 消费者端点不产生广播


# ---------- v3：握手期令牌认证 ----------


def test_upload_without_token_rejected(client: TestClient, ws_manager: StubManager) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/upload/3") as ws:
            ws.receive_text()  # 消费关闭帧以触发异常
    assert exc_info.value.code == 4401
    assert ws_manager.broadcasts == []  # 拒绝发生在任何业务处理之前


def test_upload_with_garbage_token_rejected(client: TestClient, ws_manager: StubManager) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/upload/3?token=not-a-jwt") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4401


def test_upload_by_viewer_forbidden(client: TestClient, ws_manager: StubManager) -> None:
    _make_user("viewer1", "viewer-pass-123", "viewer")
    token = _login_token(client, "viewer1", "viewer-pass-123")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/upload/3?token={token}") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4403  # 令牌有效但角色不足
    assert ws_manager.broadcasts == []


def test_realtime_by_viewer_allowed(client: TestClient, ws_manager: StubManager) -> None:
    """viewer 只读：观看实时流应放行（与 REST 读权限策略对齐）"""
    _make_user("viewer2", "viewer-pass-123", "viewer")
    token = _login_token(client, "viewer2", "viewer-pass-123")

    with client.websocket_connect(f"/ws/realtime/7?token={token}"):
        pass

    assert ws_manager.connected == [7]  # 正常订阅


def test_realtime_without_token_rejected(client: TestClient, ws_manager: StubManager) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/realtime/5") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4401
    assert ws_manager.connected == []
