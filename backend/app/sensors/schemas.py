"""传感器批量上报的请求契约

字段与 sensor_snapshots 表列一一对应（timestamp → record_time 在端点内映射）。
extra="ignore"：丢弃链路字段（如 type），只校验持久化所需数据。
"""

from datetime import UTC, datetime

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
