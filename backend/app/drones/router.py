"""设备 CRUD 端点：分页列表（筛选）、详情、创建、更新、删除

权限模型：
- 读（列表/详情）：任何认证用户（get_current_user，三种角色均可）
- 写（创建/更新/删除）：operator / admin

查询设计：
- status / model 精确过滤——分别命中 idx_status、idx_model 索引
- 固定按 id 倒序（新设备在前），不开放任意排序（防过度设计）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.rbac import require_roles
from app.db import get_db
from app.dependencies import get_current_user
from app.drones.schemas import DroneCreate, DroneOut, DronePage, DroneUpdate
from app.models import Drone, User

router = APIRouter(prefix="/drones", tags=["drones"])


@router.get("", response_model=DronePage)
def list_drones(
    status: str | None = Query(default=None, description="按状态过滤"),
    model: str | None = Query(default=None, description="按机型过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DronePage:
    stmt = select(Drone)
    if status is not None:
        stmt = stmt.where(Drone.status == status)
    if model is not None:
        stmt = stmt.where(Drone.model == model)

    # COUNT 与数据查询同源：先构造过滤后的基础查询再分别派生，
    # 保证 total 与 items 永远一致
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Drone.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return DronePage(
        items=[DroneOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{drone_id}", response_model=DroneOut)
def get_drone(
    drone_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Drone:
    drone = db.get(Drone, drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return drone


@router.post("", response_model=DroneOut, status_code=201)
def create_drone(
    body: DroneCreate,
    _user: User = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> Drone:
    drone = Drone(**body.model_dump())
    db.add(drone)
    db.commit()
    db.refresh(drone)
    return drone


@router.patch("/{drone_id}", response_model=DroneOut)
def update_drone(
    drone_id: int,
    body: DroneUpdate,
    _user: User = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> Drone:
    drone = db.get(Drone, drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    updates = body.model_dump(exclude_unset=True)  # 只更新显式传入的字段
    for field, value in updates.items():
        setattr(drone, field, value)
    db.commit()
    db.refresh(drone)
    return drone


@router.delete("/{drone_id}", status_code=204)
def delete_drone(
    drone_id: int,
    _user: User = Depends(require_roles("operator")),
    db: Session = Depends(get_db),
) -> None:
    drone = db.get(Drone, drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.delete(drone)
    db.commit()
