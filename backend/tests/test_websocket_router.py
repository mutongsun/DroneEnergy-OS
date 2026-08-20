"""WS 端点集成测试：上行帧 → 广播接线（Week 2 转发链路）

TestClient 不走 lifespan，因此用替身注入 app.state.ws_manager，
只验证端点对 manager 的调用契约：
- 上行 sensor_frame → send_sensor_frame(drone_id, msg)
- 非 JSON 上行 → 忽略且不断连
- 连接关闭 → disconnect 幂等清理
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


def test_upstream_frame_is_broadcast(client: TestClient, ws_manager: StubManager) -> None:
    frame = {"type": "sensor_frame", "voltage_v": 22.1, "battery_soc_percent": 88.5}
    with client.websocket_connect("/ws/realtime/3") as ws:
        ws.send_text(json.dumps(frame))
        ws.send_text("not-a-json")  # 非 JSON 上行：忽略且不断连
        ws.send_text(json.dumps({"type": "unknown"}))  # 未知类型：不广播

    assert ws_manager.connected == [3]
    assert ws_manager.broadcasts == [(3, frame)]
    assert ws_manager.disconnected == [3]  # finally 兜底清理
