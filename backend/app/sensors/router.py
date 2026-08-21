"""传感器端点：批量入库 + 历史查询

实现说明：
- 同步 def + 同步 SQLAlchemy 会话：FastAPI 自动放入线程池执行，
  不阻塞事件循环（批量 ≤100 行的 bulk insert 为毫秒级）
- 持久化路径与实时路径解耦：入库端点只负责落库；
  实时转发（WS → 浏览器）由 websocket 模块负责
- 历史查询限幅 ≤2000 点（按 1Hz ≈ 33 分钟），防止前端一次拉穿数据库
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.auth.rbac import require_roles
from app.db import get_db
from app.dependencies import get_current_user
from app.models import SensorSnapshot, User
from app.monitoring.metrics import SENSOR_FRAMES_WRITTEN_TOTAL
from app.sensors.schemas import (
    BatchAccepted,
    HistoryOut,
    HistoryPoint,
    SensorBatchIn,
    SensorFrameIn,
)

router = APIRouter(prefix="/sensor", tags=["sensors"])


def _to_row(frame: SensorFrameIn) -> dict[str, Any]:
    data = frame.model_dump(exclude={"timestamp"})
    data["record_time"] = frame.timestamp
    return data


@router.post("/batch", response_model=BatchAccepted)
def upload_batch(
    payload: SensorBatchIn,
    _user: User = Depends(require_roles("operator", "admin")),
    db: Session = Depends(get_db),
) -> BatchAccepted:
    rows = [_to_row(f) for f in payload.frames]
    db.execute(insert(SensorSnapshot).values(rows))
    db.commit()
    SENSOR_FRAMES_WRITTEN_TOTAL.inc(len(rows))
    return BatchAccepted(accepted=len(rows))


@router.get("/history/{drone_id}", response_model=HistoryOut)
def get_history(
    drone_id: int,
    minutes: int = Query(default=10, ge=1, le=60),
    limit: int = Query(default=600, ge=1, le=2000),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryOut:
    """最近 N 分钟历史曲线（时间升序）；limit 截尾保护大时间窗查询"""
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes)
    rows = db.scalars(
        select(SensorSnapshot)
        .where(SensorSnapshot.drone_id == drone_id, SensorSnapshot.record_time >= since)
        .order_by(SensorSnapshot.record_time.desc())
        .limit(limit)
    ).all()
    rows.reverse()  # 升序返回，图表直接消费
    return HistoryOut(
        drone_id=drone_id,
        minutes=minutes,
        points=[HistoryPoint.model_validate(r) for r in rows],
    )


def latest_frames(db: Session, drone_id: int, count: int = 60) -> list[SensorSnapshot]:
    """取最近 N 帧供 AI 诊断（时间升序）"""
    rows = db.scalars(
        select(SensorSnapshot)
        .where(SensorSnapshot.drone_id == drone_id)
        .order_by(SensorSnapshot.record_time.desc())
        .limit(count)
    ).all()
    rows.reverse()
    return rows
