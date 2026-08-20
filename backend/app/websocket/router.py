"""WebSocket 端点：连接生命周期与传感器帧入口"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.monitoring.metrics import SENSOR_FRAMES_RECEIVED_TOTAL

router = APIRouter()


@router.websocket("/ws/realtime/{drone_id}")
async def realtime(ws: WebSocket, drone_id: int) -> None:
    manager = ws.app.state.ws_manager
    await manager.connect(ws, drone_id)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue  # 非 JSON 上行直接忽略，不中断连接
            if msg.get("type") == "sensor_frame":
                SENSOR_FRAMES_RECEIVED_TOTAL.inc()
                # 实时转发：经 Redis PubSub 扇出到所有副本上订阅该无人机的浏览器；
                # 持久化由 POST /api/v1/sensor/batch（模拟器批量上报）承担，
                # WS 链路只负责实时观看，不落库
                await manager.send_sensor_frame(drone_id, msg)
    except WebSocketDisconnect:
        pass
    finally:
        # 统一走幂等清理：与心跳协程的自动清理互为兜底
        await manager.disconnect(ws, drone_id)
