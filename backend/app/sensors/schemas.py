"""传感器数据契约：入库（批量）+ 历史查询"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SensorFrameIn(BaseModel):
    """单帧 20 维传感器数据"""

    model_config = ConfigDict(extra="ignore")

    drone_id: int
    timestamp: datetime
    flight_id: int | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    battery_temp_c: float | None = None
    motor_temp_c: float | None = None
    ambient_temp_c: float | None = None
    spin_thermal_power_w: float | None = None
    spin_thermal_voltage_mv: float | None = None
    magnetic_x: float | None = None
    magnetic_y: float | None = None
    magnetic_z: float | None = None
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None
    altitude_m: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    roll_deg: float | None = None
    gps_lat: float | None = None
    gps_lng: float | None = None
    battery_soc_percent: float | None = None
    fault_code: int | None = 0

    @field_validator("timestamp", mode="after")
    @classmethod
    def _utc_naive(cls, v: datetime) -> datetime:
        # MySQL DATETIME 无时区语义：统一转 UTC 再剥离 tzinfo，
        # 避免驱动把带偏移的时间串写进 DATETIME(3) 列
        return v.astimezone(UTC).replace(tzinfo=None) if v.tzinfo else v


class SensorBatchIn(BaseModel):
    """批量上报：1~100 帧/批（防止超大请求体打爆线程池与 max_allowed_packet）"""

    frames: list[SensorFrameIn] = Field(min_length=1, max_length=100)


class BatchAccepted(BaseModel):
    accepted: int


class HistoryPoint(BaseModel):
    """历史曲线点：只暴露可视化与诊断所需的核心维度"""

    model_config = ConfigDict(from_attributes=True)

    record_time: datetime
    voltage_v: float | None = None
    current_a: float | None = None
    battery_temp_c: float | None = None
    motor_temp_c: float | None = None
    spin_thermal_power_w: float | None = None
    altitude_m: float | None = None
    battery_soc_percent: float | None = None
    fault_code: int | None = 0


class HistoryOut(BaseModel):
    """历史查询响应（时间升序）"""

    drone_id: int
    minutes: int
    points: list[HistoryPoint]


def build_flight_context(rows: list[Any]) -> dict[str, Any]:
    """把最近若干帧聚合成 DeepSeek 诊断上下文（均值 + 最新值 + 异常计数）"""
    if not rows:
        return {"has_data": False}

    def avg(field: str) -> float:
        vals = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        # float()：ORM Numeric 列返回 Decimal，JSON 列/响应序列化都不接受
        return round(float(sum(vals)) / len(vals), 2) if vals else 0.0

    latest = rows[-1]
    faults = [r for r in rows if (r.fault_code or 0) != 0]
    return {
        "has_data": True,
        "sample_count": len(rows),
        "model": "unknown",  # 由路由层补充设备机型
        "soc": float(latest.battery_soc_percent or 0),
        "battery_temp": avg("battery_temp_c"),
        "motor_temp": avg("motor_temp_c"),
        "thermal_power": avg("spin_thermal_power_w"),
        "wind_speed": avg("wind_speed_ms"),
        "voltage_avg": avg("voltage_v"),
        "current_avg": avg("current_a"),
        "fault_count": len(faults),
        "latest_fault_code": latest.fault_code or 0,
        "phase": "cruise",  # 简化：历史数据无阶段字段
    }
