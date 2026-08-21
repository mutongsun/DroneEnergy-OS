"""DroneEnergy-OS 压测脚本（Locust）

场景与 README「压测报告模板」对应：
- RestReader  场景 A：REST 读负载（设备列表 + 历史曲线查询）
- BatchWriter 场景 C：批量写入（POST /api/v1/sensor/batch，100 帧/批）

用法（headless，分别跑两个场景）：
    locust -f locustfile.py RestReader  --headless -u 100 -r 10 -t 3m --csv result_rest
    locust -f locustfile.py BatchWriter --headless -u 10  -r 2  -t 2m --csv result_batch

场景 B（WS 扇出）见 loadtest_ws.py（asyncio 脚本，非 Locust）。
"""

import random
import time
from datetime import UTC, datetime

from locust import HttpUser, between, task


def _frame(drone_id: int) -> dict:
    """构造一帧合法的 20 维传感器数据（与模拟器字段一致）"""
    return {
        "drone_id": drone_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "voltage_v": round(22.2 - random.uniform(0, 1), 2),
        "current_a": round(random.uniform(5, 20), 2),
        "battery_temp_c": round(25 + random.uniform(0, 12), 1),
        "motor_temp_c": round(30 + random.uniform(0, 20), 1),
        "ambient_temp_c": round(22 + random.uniform(-3, 3), 1),
        "spin_thermal_power_w": round(random.uniform(8, 15), 2),
        "spin_thermal_voltage_mv": round(random.uniform(18, 28), 2),
        "magnetic_x": round(random.uniform(-50, 50), 3),
        "magnetic_y": round(random.uniform(-50, 50), 3),
        "magnetic_z": round(random.uniform(200, 300), 3),
        "wind_speed_ms": round(random.uniform(0, 13.8), 2),
        "wind_direction_deg": round(random.uniform(0, 360), 1),
        "altitude_m": round(random.uniform(40, 100), 2),
        "pitch_deg": round(random.uniform(-15, 15), 2),
        "yaw_deg": round(random.uniform(-180, 180), 2),
        "roll_deg": round(random.uniform(-10, 10), 2),
        "gps_lat": round(39.9042 + random.uniform(-0.001, 0.001), 6),
        "gps_lng": round(116.4074 + random.uniform(-0.001, 0.001), 6),
        "battery_soc_percent": round(random.uniform(20, 100), 2),
        "fault_code": 0,
    }


class _AuthedUser(HttpUser):
    """公共基类：启动时登录一次，后续请求带 Bearer 令牌"""

    abstract = True
    # 压测目标：宿主机映射端口 8001（见 docker-compose.yml 端口说明）
    host = "http://localhost:8001"

    username = "operator"
    password = "operator123"

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": self.username, "password": self.password},
            name="/api/v1/auth/login",
        )
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            self.client.headers["Authorization"] = f"Bearer {token}"
        else:
            raise RuntimeError(f"login failed: {resp.status_code} {resp.text}")


class RestReader(_AuthedUser):
    """场景 A：模拟前端轮询行为——设备下拉列表 + 历史曲线拉取"""

    wait_time = between(0.5, 1.5)  # 间隔 0.5~1.5s，模拟真实用户节奏

    @task(1)
    def list_drones(self) -> None:
        self.client.get("/api/v1/drones?page=1&page_size=20", name="/api/v1/drones")

    @task(3)
    def get_history(self) -> None:
        drone_id = random.choice([1, 2, 3])
        self.client.get(
            f"/api/v1/sensor/history/{drone_id}?minutes=10&limit=600",
            name="/api/v1/sensor/history/[id]",
        )


class BatchWriter(_AuthedUser):
    """场景 C：模拟数据上报端——满批 100 帧连续写入"""

    wait_time = between(0.05, 0.15)  # 上报端高频节奏

    @task
    def post_batch(self) -> None:
        frames = [_frame(random.choice([1, 2, 3])) for _ in range(100)]
        t0 = time.perf_counter()
        with self.client.post(
            "/api/v1/sensor/batch", json={"frames": frames}, name="/api/v1/sensor/batch"
        ) as resp:
            if resp.status_code == 200:
                resp.elapsed_ms = (time.perf_counter() - t0) * 1000  # noqa: F841
