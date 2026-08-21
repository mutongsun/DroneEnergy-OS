"""传感器历史查询 + AI 诊断端点测试（AI 客户端用替身，不打真实 API）"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _seed_frames(client: TestClient, headers: dict[str, str], drone_id: int, count: int) -> None:
    now = datetime.now(UTC)
    frames = [
        {
            "drone_id": drone_id,
            "timestamp": (now - timedelta(seconds=count - i)).isoformat(),
            "voltage_v": 22.0,
            "current_a": 10.0,
            "battery_temp_c": 30.0,
            "motor_temp_c": 45.0,
            "spin_thermal_power_w": 12.0,
            "battery_soc_percent": 80.0,
            "fault_code": 0,
        }
        for i in range(count)
    ]
    resp = client.post("/api/v1/sensor/batch", json={"frames": frames}, headers=headers)
    assert resp.status_code == 200, resp.text


class StubAiClient:
    """替身：不触发外呼，模拟模型返回与 fallback 两种路径"""

    def __init__(self) -> None:
        self.response: dict[str, Any] = {
            "action": "increase_thermal_priority",
            "params": {"confidence": 0.85, "thermal_ratio": 0.7},
            "reason": "SOC 下降较快，建议热电优先供电",
        }
        self.calls: list[dict[str, Any]] = []

    async def chat(self, ctx: dict[str, Any], query: str) -> dict[str, Any]:
        self.calls.append({"ctx": ctx, "query": query})
        return self.response


@pytest.fixture
def ai_client() -> StubAiClient:
    stub = StubAiClient()
    app.state.ai_client = stub
    yield stub
    del app.state.ai_client


def test_history_returns_points(client: TestClient, login) -> None:
    headers = login("op", "op123", "operator")
    _seed_frames(client, headers, drone_id=1, count=5)

    resp = client.get("/api/v1/sensor/history/1?minutes=10", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["drone_id"] == 1
    assert len(body["points"]) == 5
    # 升序：record_time 递增
    times = [p["record_time"] for p in body["points"]]
    assert times == sorted(times)


def test_history_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/sensor/history/1").status_code == 401


def test_diagnose_returns_decision_and_persists(
    client: TestClient, login, ai_client: StubAiClient
) -> None:
    headers = login("op", "op123", "operator")
    # 建设备 + 播数据
    client.post(
        "/api/v1/drones",
        json={"name": "测试机", "model": "DJI_Mavic3", "status": "flying", "max_battery_mah": 5000},
        headers=headers,
    )
    _seed_frames(client, headers, drone_id=1, count=3)

    resp = client.post(
        "/api/v1/ai/diagnose",
        json={"drone_id": 1, "query": "能源状态如何？"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "increase_thermal_priority"
    assert body["fell_back"] is False
    assert body["decision_type"] == "power_alloc"
    assert body["confidence"] == 0.85
    # 上下文含机型与数据聚合
    ctx = ai_client.calls[0]["ctx"]
    assert ctx["model"] == "DJI_Mavic3"
    assert ctx["has_data"] is True


def test_diagnose_fallback_flows_through(
    client: TestClient, login, ai_client: StubAiClient
) -> None:
    headers = login("op", "op123", "operator")
    ai_client.response = {"action": "fallback", "params": {}, "reason": "AI 不可用"}

    client.post(
        "/api/v1/drones",
        json={
            "name": "测试机",
            "model": "XAG_P80Pro",
            "status": "flying",
            "max_battery_mah": 12000,
        },
        headers=headers,
    )
    resp = client.post("/api/v1/ai/diagnose", json={"drone_id": 1}, headers=headers)
    assert resp.status_code == 200  # fallback 也是 200：前端永远有建议可用
    assert resp.json()["fell_back"] is True


def test_diagnose_404_unknown_drone(client: TestClient, login, ai_client: StubAiClient) -> None:
    headers = login("op", "op123", "operator")
    resp = client.post("/api/v1/ai/diagnose", json={"drone_id": 999}, headers=headers)
    assert resp.status_code == 404


def test_diagnose_viewer_forbidden(client: TestClient, login, ai_client: StubAiClient) -> None:
    headers = login("view", "view123", "viewer")
    resp = client.post("/api/v1/ai/diagnose", json={"drone_id": 1}, headers=headers)
    assert resp.status_code == 403
