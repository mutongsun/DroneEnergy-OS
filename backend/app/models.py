"""ORM 模型

重要约定：flight_logs / sensor_snapshots 是 MySQL 分区表。
声明式模型只映射列结构；PARTITION 子句由 Alembic 原生 SQL 迁移维护
（见 alembic/versions/0001_initial.py）。因此：
1. 不要对这两张表执行 Base.metadata.create_all()
2. 不要依赖 autogenerate 管理这两张表的 DDL
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 主键跨方言兼容：MySQL 用 BIGINT，SQLite（单元测试）退化为 INTEGER
# —— SQLite 只有 INTEGER PRIMARY KEY 才有自增 rowid 语义
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("admin", "operator", "viewer", name="user_role"),
        default="viewer",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False, comment="机型")
    status: Mapped[str] = mapped_column(
        Enum("idle", "flying", "maintenance", "offline", name="drone_status"),
        default="idle",
        nullable=False,
    )
    max_battery_mah: Mapped[int] = mapped_column(Integer, default=5000)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FlightLog(Base):
    """飞行记录主表（按 flight_date 分区，见文件头说明）"""

    __tablename__ = "flight_logs"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    drone_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    flight_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    total_distance_m: Mapped[float | None] = mapped_column(Numeric(10, 2))
    avg_speed_ms: Mapped[float | None] = mapped_column(Numeric(5, 2))
    battery_consumed_mah: Mapped[int | None] = mapped_column(Integer)
    thermal_energy_recovered_mj: Mapped[float | None] = mapped_column(
        Numeric(8, 2), comment="自旋热电回收能量"
    )
    soc_drop_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))


class SensorSnapshot(Base):
    """传感器时序快照（按 record_time 分区，见文件头说明）"""

    __tablename__ = "sensor_snapshots"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # 可空：传感器数据可能先于飞行记录产生（见迁移 0002）
    flight_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    drone_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    record_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    voltage_v: Mapped[float | None] = mapped_column(Numeric(5, 2))
    current_a: Mapped[float | None] = mapped_column(Numeric(5, 2))
    battery_temp_c: Mapped[float | None] = mapped_column(Numeric(4, 1))
    motor_temp_c: Mapped[float | None] = mapped_column(Numeric(4, 1))
    ambient_temp_c: Mapped[float | None] = mapped_column(Numeric(4, 1))
    spin_thermal_power_w: Mapped[float | None] = mapped_column(Numeric(6, 2))
    spin_thermal_voltage_mv: Mapped[float | None] = mapped_column(Numeric(6, 2))
    magnetic_x: Mapped[float | None] = mapped_column(Numeric(7, 3))
    magnetic_y: Mapped[float | None] = mapped_column(Numeric(7, 3))
    magnetic_z: Mapped[float | None] = mapped_column(Numeric(7, 3))
    wind_speed_ms: Mapped[float | None] = mapped_column(Numeric(4, 2))
    wind_direction_deg: Mapped[float | None] = mapped_column(Numeric(5, 1))
    altitude_m: Mapped[float | None] = mapped_column(Numeric(7, 2))
    pitch_deg: Mapped[float | None] = mapped_column(Numeric(5, 2))
    yaw_deg: Mapped[float | None] = mapped_column(Numeric(5, 2))
    roll_deg: Mapped[float | None] = mapped_column(Numeric(5, 2))
    gps_lat: Mapped[float | None] = mapped_column(Numeric(10, 6))
    gps_lng: Mapped[float | None] = mapped_column(Numeric(10, 6))
    battery_soc_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    fault_code: Mapped[int | None] = mapped_column(Integer, default=0)


class AiDecision(Base):
    __tablename__ = "ai_decisions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    flight_id: Mapped[int | None] = mapped_column(BigInteger)
    drone_id: Mapped[int | None] = mapped_column(BigInteger)
    decision_type: Mapped[str | None] = mapped_column(
        Enum("power_alloc", "fault_warn", "route_optimize", name="decision_type")
    )
    input_context: Mapped[dict | None] = mapped_column(JSON, comment="输入给模型的上下文")
    raw_response: Mapped[str | None] = mapped_column(String(4000), comment="模型原始输出")
    parsed_action: Mapped[dict | None] = mapped_column(JSON, comment="结构化动作")
    confidence_score: Mapped[float | None] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
