"""WebSocket 连接管理器（v2 修正版）

v1 的两个缺陷：
1. active_connections 为进程内字典——部署多个后端副本时，
   模拟器连在副本 A 上，副本 B 的浏览器收不到任何广播，水平扩展为零。
2. 心跳协程用裸 except + del 清理——吞掉所有异常（含 CancelledError），
   任务引用未被 cancel，存在协程泄漏与竞态。

v2 修正：
1. 跨副本广播：发布方只向 Redis PubSub publish 一次，
   每个副本的监听协程负责把消息转发给「本副本」持有的连接。
2. 心跳任务生命周期显式管理：disconnect 统一 cancel，
   清理逻辑幂等（可被心跳协程与端点 finally 重复触发而不产生副作用）。
"""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.monitoring.metrics import WS_ACTIVE_CONNECTIONS, WS_MESSAGES_SENT_TOTAL

logger = logging.getLogger(__name__)

# 跨副本广播频道：消息体为 {"drone_id": int, "data": {...}}
BROADCAST_CHANNEL = "ws:broadcast"


class ConnectionManager:
    """每个后端副本持有一个实例；跨副本消息经 Redis PubSub 扇出"""

    def __init__(self, redis: Redis, heartbeat_interval: int = 30) -> None:
        self._redis = redis
        self._heartbeat_interval = heartbeat_interval
        # drone_id → 本副本持有的连接集合（同一无人机可能被多个浏览器同时观看）
        self._local: dict[int, set[WebSocket]] = {}
        # 连接 → 心跳任务；disconnect 时统一取消，杜绝协程泄漏
        self._heartbeat_tasks: dict[WebSocket, asyncio.Task[None]] = {}
        self._listener_task: asyncio.Task[None] | None = None
        self._listener_ready = asyncio.Event()

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        """应用启动时调用：启动 Redis 广播监听协程，等待订阅生效后返回"""
        self._listener_ready.clear()
        self._listener_task = asyncio.create_task(
            self._listen_broadcast(), name="ws-redis-listener"
        )
        # 等待订阅真正生效，避免启动窗口期内的消息被静默丢弃
        await self._listener_ready.wait()

    async def stop(self) -> None:
        """应用关停时调用：取消监听与全部心跳任务"""
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        for task in self._heartbeat_tasks.values():
            task.cancel()
        self._heartbeat_tasks.clear()
        self._local.clear()

    # ---------- 连接管理 ----------

    async def connect(self, ws: WebSocket, drone_id: int) -> None:
        await ws.accept()
        self._local.setdefault(drone_id, set()).add(ws)
        self._heartbeat_tasks[ws] = asyncio.create_task(
            self._heartbeat(ws, drone_id), name=f"ws-heartbeat-{drone_id}"
        )
        WS_ACTIVE_CONNECTIONS.inc()
        logger.info("ws_connected drone_id=%s", drone_id)

    async def disconnect(self, ws: WebSocket, drone_id: int) -> None:
        """幂等清理：心跳协程与端点 finally 都可能调用"""
        task = self._heartbeat_tasks.pop(ws, None)
        if task is not None and not task.done():
            task.cancel()
        await self._cleanup(ws, drone_id)

    async def _cleanup(self, ws: WebSocket, drone_id: int) -> None:
        conns = self._local.get(drone_id)
        removed = conns is not None and ws in conns
        if conns is not None:
            conns.discard(ws)
            if not conns:
                self._local.pop(drone_id, None)
        if removed:  # 仅首次移除时递减指标，保证幂等
            WS_ACTIVE_CONNECTIONS.dec()
        logger.info("ws_disconnected drone_id=%s", drone_id)

    # ---------- 消息广播 ----------

    async def send_sensor_frame(self, drone_id: int, data: dict[str, Any]) -> None:
        """发布传感器帧：任一副本上的监听协程都会向本地连接转发"""
        payload = json.dumps({"drone_id": drone_id, "data": data}, ensure_ascii=False)
        await self._redis.publish(BROADCAST_CHANNEL, payload)

    async def _forward_to_local(self, drone_id: int, message: str) -> None:
        # 迭代快照：转发中某个连接失败会触发 disconnect 修改集合
        for ws in list(self._local.get(drone_id, ())):
            try:
                await ws.send_text(message)
                WS_MESSAGES_SENT_TOTAL.labels(str(drone_id)).inc()
            except (WebSocketDisconnect, RuntimeError):
                logger.warning("ws_send_failed drone_id=%s", drone_id)
                await self.disconnect(ws, drone_id)

    async def _listen_broadcast(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(BROADCAST_CHANNEL)
        self._listener_ready.set()
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue  # 跳过订阅确认等控制消息
                body = json.loads(msg["data"])
                await self._forward_to_local(
                    body["drone_id"], json.dumps(body["data"], ensure_ascii=False)
                )
        except asyncio.CancelledError:
            raise  # 应用关停时正常退出
        finally:
            await pubsub.aclose()

    # ---------- 心跳 ----------

    async def _heartbeat(self, ws: WebSocket, drone_id: int) -> None:
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                await ws.send_text(json.dumps({"type": "ping", "ts": time.time()}))
        except asyncio.CancelledError:
            raise  # 由 disconnect 主动取消，属正常关停
        except (WebSocketDisconnect, RuntimeError):
            # 连接已死：只做幂等清理，不 cancel 自身（取消已由 disconnect 负责）
            await self._cleanup(ws, drone_id)
