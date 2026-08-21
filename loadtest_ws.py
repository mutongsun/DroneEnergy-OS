"""场景 B：WS 实时订阅扇出压测（asyncio 脚本，非 Locust）

N 个并发观看端订阅 /ws/realtime/{drone_id}，统计：
- 每端实际收到的帧率（目标 ≈ 60 帧/分 = 1Hz × 3 架无人机中该机 1Hz）
- 断连次数（含 4401/4403 认证关闭）
- 每端首帧延迟

用法：
    .venv-loadtest/Scripts/python.exe loadtest_ws.py --clients 100 --duration 180
"""

import argparse
import asyncio
import json
import os
import time

import websockets

# 默认走宿主机端口映射（Windows Docker 代理）；容器内直连时用
# LOADTEST_API=http://backend:8000/... LOADTEST_WS_BASE=ws://backend:8000 覆盖
API = os.getenv("LOADTEST_API", "http://localhost:8001/api/v1/auth/login")
WS_BASE = os.getenv("LOADTEST_WS_BASE", "ws://localhost:8001")


def fetch_token() -> str:
    """登录 viewer 账号拿令牌（WS v3 认证）。仅启动时调用一次，
    用标准库 urllib 即可——便于在仅有 websockets 依赖的后端容器内复用本脚本。"""
    import urllib.request

    creds = json.dumps({"username": "viewer", "password": "viewer123"}).encode()
    req = urllib.request.Request(
        API, data=creds, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]


class Subscriber:
    def __init__(self, token: str, drone_id: int) -> None:
        self.token = token
        self.drone_id = drone_id
        self.frames = 0
        self.disconnects = 0
        self.first_frame_latency: float | None = None
        self.closed_codes: list[int] = []

    async def run(self, duration: float) -> None:
        deadline = time.monotonic() + duration
        url = f"{WS_BASE}/ws/realtime/{self.drone_id}?token={self.token}"
        while time.monotonic() < deadline:
            try:
                t0 = time.monotonic()
                async with websockets.connect(url) as ws:
                    async for raw in ws:
                        if time.monotonic() > deadline:
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if msg.get("type") != "sensor_frame":
                            continue  # 心跳 ping
                        if self.first_frame_latency is None:
                            self.first_frame_latency = time.monotonic() - t0
                        self.frames += 1
            except websockets.ConnectionClosed as exc:
                self.disconnects += 1
                self.closed_codes.append(exc.code)
                await asyncio.sleep(0.5)
            except OSError:
                self.disconnects += 1
                await asyncio.sleep(0.5)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", type=int, default=100)
    parser.add_argument("--duration", type=float, default=180.0)
    args = parser.parse_args()

    token = fetch_token()
    subs = [Subscriber(token, (i % 3) + 1) for i in range(args.clients)]

    print(f"[ws-fanout] clients={args.clients} duration={args.duration:.0f}s ...")
    t0 = time.monotonic()
    await asyncio.gather(*(s.run(args.duration) for s in subs))
    wall = time.monotonic() - t0

    rates = [s.frames / (wall / 60) for s in subs]
    firsts = [s.first_frame_latency for s in subs if s.first_frame_latency is not None]
    disconnects = sum(s.disconnects for s in subs)
    codes: dict[int, int] = {}
    for s in subs:
        for c in s.closed_codes:
            codes[c] = codes.get(c, 0) + 1

    rates.sort()
    print(f"[ws-fanout] wall={wall:.1f}s")
    print(f"  frames/client/min: min={rates[0]:.1f} median={rates[len(rates)//2]:.1f} max={rates[-1]:.1f}")
    if firsts:
        firsts.sort()
        print(f"  first-frame latency(s): p50={firsts[len(firsts)//2]:.2f} max={firsts[-1]:.2f}")
    print(f"  total disconnects={disconnects} close_codes={codes or 'none'}")
    print(f"  total frames received={sum(s.frames for s in subs)}")


if __name__ == "__main__":
    asyncio.run(main())
