"""WS 端点集成测试：生产者/消费者端点分离（v2 架构）

TestClient 不走 lifespan，因此用替身注入 app.state.ws_manager，
验证端点对 manager 的调用契约：
- /ws/upload/{id}：上行 sensor_frame → send_sensor_frame（不注册订阅）
- /ws/realtime/{id}：注册订阅；断开时幂等清理
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

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


def test_upload_endpoint_broadcasts_frames(client: TestClient, ws_manager: StubManager) -> None:
    frame = {"type": "sensor_frame", "voltage_v": 22.1, "battery_soc_percent": 88.5}
    with client.websocket_connect("/ws/upload/3") as ws:
        ws.send_text(json.dumps(frame))
        ws.send_text("not-a-json")  # 非 JSON 上行：忽略且不断连
        ws.send_text(json.dumps({"type": "unknown"}))  # 未知类型：不广播

    assert ws_manager.broadcasts == [(3, frame)]
    assert ws_manager.connected == []  # 生产者不注册订阅表（无回声）


def test_realtime_endpoint_subscribes(client: TestClient, ws_manager: StubManager) -> None:
    with client.websocket_connect("/ws/realtime/5"):
        pass  # 立即关闭

    assert ws_manager.connected == [5]
    assert ws_manager.disconnected == [5]  # finally 兜底清理
    assert ws_manager.broadcasts == []  # 消费者端点不产生广播
