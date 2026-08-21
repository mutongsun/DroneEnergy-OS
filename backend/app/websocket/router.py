"""WebSocket 端点：数据上传与实时订阅分离（v3：握手期令牌认证）

v1 缺陷：生产者（模拟器）与消费者（浏览器）共用一个端点，广播会把帧
回声给数据源自身——模拟器只发不读，回声堆积撑满接收队列后停止读 TCP，
双向 keepalive ping/pong 随之堵塞，约 40 秒后连接必然超时断开。

v2 修正：
- /ws/upload/{drone_id}   生产者入口：只收帧、发布广播，不注册订阅表
- /ws/realtime/{drone_id} 消费者入口：注册订阅 + 服务端心跳，不处理上行

v3 增强：WS 握手期令牌认证
- 浏览器 WebSocket API 不支持自定义请求头，令牌经查询参数 ?token=<jwt> 传递
- 角色策略与 REST 对齐：upload 需 operator/admin（等同 POST /sensor/batch），
  realtime 任意认证用户可观看（viewer 只读）
- 认证失败先 accept 再 close：ASGI 在 accept 前直接 close 只能拒绝握手
  （客户端收到 HTTP 403，拿不到具体原因）；携带 4401/4403 关闭码
  可让客户端区分"令牌无效"与"角色不足"
"""

import json

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db import get_db
from app.models import User
from app.monitoring.metrics import SENSOR_FRAMES_RECEIVED_TOTAL, WS_AUTH_FAILURES_TOTAL

router = APIRouter()

# 自定义关闭码（4xxx 段为应用自定义，不与协议保留码冲突）
_CLOSE_UNAUTHORIZED = 4401  # 令牌缺失/无效/过期/用户不存在
_CLOSE_FORBIDDEN = 4403  # 令牌有效但角色不足


class WsAuthError(Exception):
    """握手认证失败；code 为对应的 WS 关闭码"""

    def __init__(self, code: int) -> None:
        super().__init__(f"ws auth failed, close code {code}")
        self.code = code


async def _ws_authenticate(
    ws: WebSocket, db: Session, allowed_roles: frozenset[str] | None = None
) -> User:
    """WS 握手期认证：解析查询参数中的 JWT 并加载用户。

    - allowed_roles 为 None：任意认证用户通过（viewer 可观看实时流）
    - allowed_roles 非 None：admin 隐式放行，其余角色需命中集合（与 RBAC 惯例一致）
    - 令牌仅在握手期校验一次，长连接期间不重复验证（与 REST 无状态语义对齐）
    """
    token = ws.query_params.get("token", "")
    try:
        payload = decode_access_token(token)
        sub = payload["sub"]
        if not isinstance(sub, str):
            raise WsAuthError(_CLOSE_UNAUTHORIZED)
        user = db.get(User, int(sub))
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise WsAuthError(_CLOSE_UNAUTHORIZED) from exc
    if user is None:
        raise WsAuthError(_CLOSE_UNAUTHORIZED)
    if allowed_roles is not None and user.role != "admin" and user.role not in allowed_roles:
        raise WsAuthError(_CLOSE_FORBIDDEN)
    return user


async def _reject(ws: WebSocket, code: int) -> None:
    """认证拒绝：accept 后立即以自定义码关闭，客户端可读取关闭码定位原因"""
    WS_AUTH_FAILURES_TOTAL.labels(str(code)).inc()
    await ws.accept()
    await ws.close(code=code, reason="unauthorized")


@router.websocket("/ws/upload/{drone_id}")
async def upload(ws: WebSocket, drone_id: int, db: Session = Depends(get_db)) -> None:
    """生产者入口：接收传感器帧并发布到广播频道（需 operator/admin）"""
    try:
        await _ws_authenticate(ws, db, allowed_roles=frozenset({"operator"}))
    except WsAuthError as exc:
        await _reject(ws, exc.code)
        return

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
async def realtime(ws: WebSocket, drone_id: int, db: Session = Depends(get_db)) -> None:
    """消费者入口：注册订阅 + 心跳保活（任意认证用户）"""
    try:
        await _ws_authenticate(ws, db)
    except WsAuthError as exc:
        await _reject(ws, exc.code)
        return

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
