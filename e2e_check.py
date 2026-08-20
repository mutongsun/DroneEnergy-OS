"""端到端验证：登录 → 设备列表 → WS 订阅 5 秒（固定窗口后退出）"""
import asyncio
import json
import urllib.request

import websockets

BASE = "http://localhost:8001"


def api(path: str, token: str | None = None) -> object:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(f"{BASE}{path}", headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


async def main() -> None:
    # 1. 登录 + 设备列表（验证 utf8mb4 中文）
    login = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                f"{BASE}/api/v1/auth/login",
                data=json.dumps({"username": "operator", "password": "operator123"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        ).read()
    )
    drones = api("/api/v1/drones?page=1&page_size=10", login["access_token"])
    print(f"[1] LOGIN OK role={login['role']}; DRONES total={drones['total']}: "
          + ", ".join(d["name"] for d in drones["items"]))

    # 2. WS 订阅 drone 1：固定 6 秒窗口
    frames, pings = 0, 0
    first: dict | None = None
    async with websockets.connect("ws://localhost:8001/ws/realtime/1") as ws:
        deadline = asyncio.get_event_loop().time() + 6
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            if msg.get("type") == "sensor_frame":
                frames += 1
                first = first or msg
            elif msg.get("type") == "ping":
                pings += 1

    assert frames >= 3, f"6 秒内仅收到 {frames} 帧，实时链路异常"
    print(f"[2] REALTIME OK: {frames} frames / {pings} pings in 6s "
          f"(voltage={first['voltage_v']}V soc={first['battery_soc_percent']}%)")
    print("E2E PASS")


asyncio.run(main())
