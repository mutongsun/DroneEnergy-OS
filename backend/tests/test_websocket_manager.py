"""ConnectionManager 单元测试

覆盖 v2 修正的两个核心行为：
1. Redis PubSub 广播能转发到本副本的全部连接
2. disconnect 幂等且心跳任务被正确取消（无协程泄漏）
"""

import asyncio
import json

from fakeredis.aioredis import FakeRedis
from prometheus_client import REGISTRY

from app.websocket.manager import ConnectionManager


class FakeWebSocket:
    """满足 manager 所需接口的最小 WebSocket 替身"""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def accept(self) -> None:
        pass

    async def send_text(self, message: str) -> None:
        self.sent.append(message)


def _ws_gauge() -> float:
    return float(REGISTRY.get_sample_value("ws_active_connections") or 0.0)


async def test_broadcast_reaches_all_local_connections() -> None:
    manager = ConnectionManager(FakeRedis())
    await manager.start()  # start 会等待订阅生效，之后 publish 不会丢消息
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    await manager.connect(ws1, drone_id=1)
    await manager.connect(ws2, drone_id=1)

    await manager.send_sensor_frame(1, {"soc": 88.5})
    await asyncio.sleep(0.05)  # 等待 PubSub 监听协程完成转发

    expected = json.dumps({"soc": 88.5})
    assert expected in ws1.sent
    assert expected in ws2.sent

    await manager.disconnect(ws1, drone_id=1)
    await manager.disconnect(ws2, drone_id=1)
    await manager.stop()


async def test_disconnect_is_idempotent_and_cancels_heartbeat() -> None:
    manager = ConnectionManager(FakeRedis())
    await manager.start()
    ws = FakeWebSocket()
    baseline = _ws_gauge()  # 其他测试可能已改动全局 Gauge，用增量断言

    await manager.connect(ws, drone_id=7)
    assert _ws_gauge() == baseline + 1
    heartbeat_task = manager._heartbeat_tasks[ws]

    await manager.disconnect(ws, drone_id=7)
    await manager.disconnect(ws, drone_id=7)  # 重复清理不产生副作用

    await asyncio.sleep(0)  # 让取消落地
    assert heartbeat_task.cancelled() or heartbeat_task.done()
    assert _ws_gauge() == baseline  # 指标未被重复扣减
    assert 7 not in manager._local  # 本地连接表已清空
    await manager.stop()
