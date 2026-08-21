"""FastAPI 入口：中间件注册、指标暴露、生命周期管理

v1 → v2 变更：
- 新增 TraceId / 指标中间件，/metrics 暴露 Prometheus 抓取端点
- lifespan 中启动 WS Redis PubSub 监听（支持多副本水平扩展）

Week 1 新增：
- /api/v1/auth/*：JWT 登录换发、当前用户查询
- /api/v1/sensor/batch：传感器数据批量入库（operator/admin）
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from redis.asyncio import Redis

from app.ai.client import DeepSeekClient
from app.ai.router import router as ai_router
from app.auth.router import router as auth_router
from app.config import settings
from app.drones.router import router as drones_router
from app.middleware.observability import MetricsMiddleware, TraceIdMiddleware
from app.monitoring.logging import setup_logging
from app.sensors.router import router as sensors_router
from app.websocket.manager import ConnectionManager
from app.websocket.router import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url)
    manager = ConnectionManager(redis, heartbeat_interval=settings.ws_heartbeat_interval)
    # AI 客户端单例：进程内共享熔断器状态（多实例各自独立计数）
    app.state.ai_client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        timeout=settings.deepseek_timeout,
    )
    app.state.redis = redis
    app.state.ws_manager = manager
    await manager.start()  # Redis 订阅就绪后才对外提供服务
    yield
    await manager.stop()
    await redis.aclose()


setup_logging()
app = FastAPI(title="DroneEnergy-OS API", version="0.2.0", lifespan=lifespan)

# add_middleware 后添加者位于外层：CORS 最外层保证预检请求不被拦，
# TraceId 次之保证全链路日志可关联，Metrics 最内层计量业务耗时
app.add_middleware(MetricsMiddleware)
app.add_middleware(TraceIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(sensors_router, prefix="/api/v1")
app.include_router(drones_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")

# Prometheus 抓取端点（make_asgi_app 为标准 ASGI 应用，非业务路由）
app.mount("/metrics", make_asgi_app())


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
