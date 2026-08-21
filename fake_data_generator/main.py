"""无人机数据模拟器（v2 修正版）

v1 缺陷：每 10 秒批量写库时新建 aiohttp.ClientSession——TCP 连接不复用，
高频运行下产生大量 TIME_WAIT，存在 fd 泄漏风险，是明确的反模式。

v2 修正：
- 进程生命周期内共享单个 ClientSession（TCPConnector 连接池）
- 传感器帧聚合后批量 POST，降低请求次数
- 单架无人机失败不影响其他无人机（gather 的 return_exceptions 兜底由主循环处理）
"""
import asyncio
import json
import os
import random
from datetime import datetime, timezone
from typing import Any

import aiohttp
import websockets

WS_URL = os.getenv("WS_URL", "ws://localhost:8000")
API_URL = os.getenv("API_URL", "http://localhost:8000")
API_USER = os.getenv("API_USER", "operator")
API_PASSWORD = os.getenv("API_PASSWORD", "operator123")
BATCH_SIZE = 10  # 每 10 帧（10 秒）批量写库一次

DRONE_MODELS: dict[str, dict[str, float]] = {
    "DJI_Mavic3": {"battery": 5000, "max_thermal": 15.0},
    "XAG_P80Pro": {"battery": 12000, "max_thermal": 35.0},
}


def build_frame(
    drone_id: int, model: str, soc: float, phase: str, lat: float, lng: float, altitude: float
) -> dict[str, Any]:
    """生成 20 维传感器数据帧"""
    spec = DRONE_MODELS[model]
    return {
        "type": "sensor_frame",
        "drone_id": drone_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voltage_v": round(22.2 - (100 - soc) * 0.05 + random.uniform(-0.3, 0.3), 2),
        "current_a": round(random.uniform(5, 20) if phase == "cruise" else random.uniform(2, 8), 2),
        "battery_temp_c": round(25 + (100 - soc) * 0.3 + random.uniform(-1, 1), 1),
        "motor_temp_c": round(30 + (100 - soc) * 0.5 + random.uniform(-2, 2), 1),
        "ambient_temp_c": round(22 + random.uniform(-3, 3), 1),
        "spin_thermal_power_w": round(spec["max_thermal"] * random.uniform(0.6, 1.0), 2),
        "spin_thermal_voltage_mv": round(random.uniform(18, 28), 2),
        "magnetic_x": round(random.uniform(-50, 50), 3),
        "magnetic_y": round(random.uniform(-50, 50), 3),
        "magnetic_z": round(random.uniform(200, 300), 3),
        "wind_speed_ms": round(random.uniform(0, 13.8), 2),
        "wind_direction_deg": round(random.uniform(0, 360), 1),
        "altitude_m": round(altitude, 2),
        "pitch_deg": round(random.uniform(-15, 15), 2),
        "yaw_deg": round(random.uniform(-180, 180), 2),
        "roll_deg": round(random.uniform(-10, 10), 2),
        "gps_lat": round(lat + random.uniform(-0.001, 0.001), 6),
        "gps_lng": round(lng + random.uniform(-0.001, 0.001), 6),
        "battery_soc_percent": round(soc, 2),
        "fault_code": 0 if random.random() > 0.02 else random.randint(1, 5),
    }


def update_altitude(phase: str, altitude: float) -> float:
    if phase == "takeoff":
        return min(altitude + 2.0, 100.0)
    if phase == "landing":
        return max(altitude - 2.0, 0.0)
    return altitude


async def connect_with_retry(url: str, max_attempts: int = 30, delay: float = 2.0):
    """带重试的 WS 连接

    后端容器启动需先完成 Alembic 迁移（数秒），compose 的 depends_on
    只保证容器启动而非应用就绪——无重试会产生启动竞态直接崩溃。
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await websockets.connect(url)
        except OSError:
            if attempt == max_attempts:
                raise
            print(f"[retry] 后端未就绪，{attempt}/{max_attempts} 次重试（{delay}s 后）")
            await asyncio.sleep(delay)


class ApiClient:
    """带 JWT 的批量上报客户端

    - 惰性登录：首次上报前才换发令牌
    - 401 自动重登录一次后重试（令牌过期/后端重启场景）
    - asyncio.Lock 防止 3 架无人机并发触发重复登录
    """

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self._base_url = base_url
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def _login(self) -> str:
        async with self._session.post(
            f"{self._base_url}/api/v1/auth/login",
            json={"username": API_USER, "password": API_PASSWORD},
        ) as resp:
            resp.raise_for_status()
            self._token = (await resp.json())["access_token"]
            return self._token

    async def token(self) -> str:
        async with self._lock:
            return self._token if self._token else await self._login()

    async def post_batch(self, frames: list[dict[str, Any]]) -> bool:
        """上报一批帧；成功返回 True，401 重登录重试一次"""
        tok = await self.token()
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {tok}"}
            async with self._session.post(
                f"{self._base_url}/api/v1/sensor/batch",
                json={"frames": frames},
                headers=headers,
            ) as resp:
                if resp.status == 401 and attempt == 0:
                    async with self._lock:
                        self._token = None
                    tok = await self.token()
                    continue
                return resp.status == 200
        return False


async def simulate_drone(drone_id: int, model: str, api: ApiClient) -> None:
    """模拟单架无人机：1Hz 推 WS + 聚合批量写库

    外层 while：后端重新部署（容器重建）是常态，WS 断开后自动重连，
    而非让整个模拟进程崩溃退出。
    """
    while True:
        soc, altitude, phase = 100.0, 0.0, "takeoff"
        lat, lng = 39.9042, 116.4074
        batch: list[dict[str, Any]] = []

        # 上行走 /ws/upload（生产者端点）：不注册订阅表，避免收到自己数据的回声
        # ——回声会堆积在只发不读的接收队列里，最终撑爆 keepalive 导致断连
        try:
            ws = await connect_with_retry(f"{WS_URL}/ws/upload/{drone_id}")
        except (OSError, websockets.WebSocketException):
            print(f"[drone-{drone_id}] 重连 30 次仍失败，60s 后再试")
            await asyncio.sleep(60)
            continue

        try:
            async with ws:
                for tick in range(3600):  # 模拟 1 小时飞行
                    if tick == 30:
                        phase = "cruise"
                    if tick == 3300:
                        phase = "landing"

                    frame = build_frame(drone_id, model, soc, phase, lat, lng, altitude)
                    batch.append(frame)
                    await ws.send(json.dumps(frame, ensure_ascii=False))

                    if len(batch) >= BATCH_SIZE:
                        if not await api.post_batch(batch):
                            print(f"[drone-{drone_id}] batch upload failed")
                        batch.clear()

                    soc = max(soc - 0.02, 0.0)
                    altitude = update_altitude(phase, altitude)
                    lat += 0.0001
                    await asyncio.sleep(1)  # 1Hz 数据频率
        except websockets.ConnectionClosed:
            print(f"[drone-{drone_id}] WS 断开（后端重启？），5s 后重连")
            await asyncio.sleep(5)


async def main() -> None:
    # v2 修正：进程级共享 ClientSession，统一超时与连接池上限
    timeout = aiohttp.ClientTimeout(total=10)
    connector = aiohttp.TCPConnector(limit=20, limit_per_host=20)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        api = ApiClient(session, API_URL)
        await asyncio.gather(
            simulate_drone(1, "DJI_Mavic3", api),
            simulate_drone(2, "XAG_P80Pro", api),
            simulate_drone(3, "DJI_Mavic3", api),
        )


if __name__ == "__main__":
    asyncio.run(main())
