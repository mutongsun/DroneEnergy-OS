"""WebSocket 端点：数据上传与实时订阅分离

v1 缺陷：生产者（模拟器）与消费者（浏览器）共用一个端点，广播会把帧
回声给数据源自身——模拟器只发不读，回声堆积撑满接收队列后停止读 TCP，
双向 keepalive ping/pong 随之堵塞，约 40 秒后连接必然超时断开。

v2 修正：
- /ws/upload/{drone_id}   生产者入口：只收帧、发布广播，不注册订阅表
- /ws/realtime/{drone_id} 消费者入口：注册订阅 + 服务端心跳，不处理上行
"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.monitoring.metrics import SENSOR_FRAMES_RECEIVED_TOTAL

router = APIRouter()


@router.websocket("/ws/upload/{drone_id}")
async def upload(ws: WebSocket, drone_id: int) -> None:
    """生产者入口：接收传感器帧并发布到广播频道"""
    manager = ws.app.state.ws_manager
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue  # 非 JSON 上行直接忽略，不中断连接
            if msg.get("type") == "sensor_frame":
                SENSOR_FRAMES_RECEIVED_TOTAL.inc()
                # 持久化由 POST /api/v1/sensor/batch（模拟器批量上报）承担，
                # WS 链路只负责实时扇出，不落库
                await manager.send_sensor_frame(drone_id, msg)
    except WebSocketDisconnect:
        pass
    # 无需清理：本连接从未注册到任何订阅表


@router.websocket("/ws/realtime/{drone_id}")
async def realtime(ws: WebSocket, drone_id: int) -> None:
    """消费者入口：注册订阅 + 心跳保活"""
    manager = ws.app.state.ws_manager
    await manager.connect(ws, drone_id)
    try:
        while True:
            # 浏览器正常不发消息；循环仅为感知断连（收到即丢弃）
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # 统一走幂等清理：与心跳协程的自动清理互为兜底
        await manager.disconnect(ws, drone_id)
