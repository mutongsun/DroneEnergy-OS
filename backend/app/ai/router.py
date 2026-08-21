"""AI 诊断端点：把最近传感器数据交给 DeepSeek 分析并落库决策记录

链路：最近 60 帧 → 聚合上下文 → DeepSeek（熔断 + fallback）→ 存 ai_decisions
任何 AI 失败都返回 fallback 决策（HTTP 200），前端永远拿到可用建议。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.client import DeepSeekClient
from app.auth.rbac import require_roles
from app.db import get_db
from app.models import AiDecision, Drone, User
from app.sensors.router import latest_frames
from app.sensors.schemas import build_flight_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

# 决策类型 → action 关键词映射（模型输出自由文本，入库需受控枚举）
_DECISION_TYPES = ("power_alloc", "fault_warn", "route_optimize")


class DiagnoseIn(BaseModel):
    drone_id: int
    query: str = Field(default="当前能源状态是否有风险？", min_length=1, max_length=500)


class DiagnoseOut(BaseModel):
    drone_id: int
    action: str
    params: dict
    reason: str
    decision_type: str | None = None
    confidence: float | None = None
    fell_back: bool  # True 表示走了本地降级（模型不可用）


def _classify(action: str) -> str:
    a = action.lower()
    if "fault" in a or "故障" in a or "warn" in a or "预警" in a:
        return "fault_warn"
    if "route" in a or "航线" in a or "path" in a:
        return "route_optimize"
    return "power_alloc"


def _confidence(params: dict) -> float | None:
    c = params.get("confidence")
    return float(c) if isinstance(c, int | float) and 0 <= c <= 1 else None


@router.post("/diagnose", response_model=DiagnoseOut)
async def diagnose(
    payload: DiagnoseIn,
    request: Request,
    _user: User = Depends(require_roles("operator", "admin")),
    db: Session = Depends(get_db),
) -> DiagnoseOut:
    client: DeepSeekClient = request.app.state.ai_client

    drone = db.get(Drone, payload.drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail="drone not found")

    rows = latest_frames(db, payload.drone_id, count=60)
    ctx = build_flight_context(rows)
    ctx["model"] = drone.model  # 补充设备机型

    decision = await client.chat(ctx, payload.query)
    fell_back = decision.get("action") == "fallback"
    decision_type = _classify(str(decision.get("action", "")))
    confidence = _confidence(decision.get("params") or {})

    db.add(
        AiDecision(
            drone_id=payload.drone_id,
            decision_type=decision_type,
            input_context=ctx,
            raw_response=str(decision)[:4000],
            parsed_action=decision,
            confidence_score=confidence,
        )
    )
    db.commit()

    return DiagnoseOut(
        drone_id=payload.drone_id,
        action=str(decision.get("action", "")),
        params=decision.get("params") or {},
        reason=str(decision.get("reason", "")),
        decision_type=decision_type,
        confidence=confidence,
        fell_back=fell_back,
    )
