"""设备管理的请求/响应契约

字段约束与 DB 列宽对齐（name≤100、model≤50），
在契约层拦截超长输入，避免落到数据库才报 DataError。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DroneStatus = Literal["idle", "flying", "maintenance", "offline"]


class DroneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=50)
    status: DroneStatus = "idle"
    max_battery_mah: int = Field(default=5000, gt=0, le=100_000)


class DroneUpdate(BaseModel):
    """PATCH 部分更新：全部字段可选，None 表示不修改"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=50)
    status: DroneStatus | None = None
    max_battery_mah: int | None = Field(default=None, gt=0, le=100_000)


class DroneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    model: str
    status: DroneStatus
    max_battery_mah: int
    created_at: datetime


class DronePage(BaseModel):
    """分页响应：Element Plus 分页组件可直接消费"""

    items: list[DroneOut]
    total: int
    page: int
    page_size: int
