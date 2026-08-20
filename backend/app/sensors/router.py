"""传感器批量入库端点

实现说明：
- 同步 def + 同步 SQLAlchemy 会话：FastAPI 自动放入线程池执行，
  不阻塞事件循环（批量 ≤100 行的 bulk insert 为毫秒级）
- 持久化路径与实时路径解耦：本端点只负责落库；
  实时转发（WS → 浏览器）由 websocket 模块负责
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.auth.rbac import require_roles
from app.db import get_db
from app.models import SensorSnapshot, User
from app.monitoring.metrics import SENSOR_FRAMES_WRITTEN_TOTAL
from app.sensors.schemas import BatchAccepted, SensorBatchIn, SensorFrameIn

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
