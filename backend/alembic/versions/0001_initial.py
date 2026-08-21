"""初始表结构：users / drones / ai_decisions（声明式）
+ flight_logs / sensor_snapshots（MySQL 分区表，原生 DDL）

分区表说明：SQLAlchemy 不支持 PARTITION BY 的声明式定义，
故 flight_logs / sensor_snapshots 使用原生 SQL 迁移。
新分区（如 p202604）通过后续迁移追加，p_future 兜底保证不丢数据。

Revision ID: 0001
Revises:
Create Date: 2026-08-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 普通表 ----------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "operator", "viewer", name="user_role"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "drones",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(50), nullable=False, comment="机型"),
        sa.Column(
            "status",
            sa.Enum("idle", "flying", "maintenance", "offline", name="drone_status"),
            nullable=False,
        ),
        sa.Column("max_battery_mah", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_status", "drones", ["status"])
    op.create_index("idx_model", "drones", ["model"])

    op.create_table(
        "ai_decisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("flight_id", sa.BigInteger(), nullable=True),
        sa.Column("drone_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "decision_type",
            sa.Enum("power_alloc", "fault_warn", "route_optimize", name="decision_type"),
            nullable=True,
        ),
        sa.Column("input_context", sa.JSON(), comment="输入给模型的上下文"),
        sa.Column("raw_response", sa.String(4000), comment="模型原始输出"),
        sa.Column("parsed_action", sa.JSON(), comment="结构化动作"),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_flight", "ai_decisions", ["flight_id"])
    op.create_index("idx_drone_type", "ai_decisions", ["drone_id", "decision_type"])

    # ---------- 分区表：原生 DDL ----------
    op.execute(
        """
        CREATE TABLE flight_logs (
            id BIGINT NOT NULL AUTO_INCREMENT,
            drone_id BIGINT NOT NULL,
            flight_date DATE NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NULL,
            total_distance_m DECIMAL(10, 2) NULL,
            avg_speed_ms DECIMAL(5, 2) NULL,
            battery_consumed_mah INT NULL,
            thermal_energy_recovered_mj DECIMAL(8, 2) NULL COMMENT '自旋热电回收能量',
            soc_drop_percent DECIMAL(5, 2) NULL,
            PRIMARY KEY (id, flight_date),
            INDEX idx_drone_time (drone_id, start_time),
            INDEX idx_date_model (flight_date, drone_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        PARTITION BY RANGE (TO_DAYS(flight_date)) (
            PARTITION p202601 VALUES LESS THAN (TO_DAYS('2026-02-01')),
            PARTITION p202602 VALUES LESS THAN (TO_DAYS('2026-03-01')),
            PARTITION p202603 VALUES LESS THAN (TO_DAYS('2026-04-01')),
            PARTITION p_future VALUES LESS THAN MAXVALUE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE sensor_snapshots (
            id BIGINT NOT NULL AUTO_INCREMENT,
            flight_id BIGINT NOT NULL,
            drone_id BIGINT NOT NULL,
            record_time DATETIME(3) NOT NULL,
            voltage_v DECIMAL(5, 2) NULL,
            current_a DECIMAL(5, 2) NULL,
            battery_temp_c DECIMAL(4, 1) NULL,
            motor_temp_c DECIMAL(4, 1) NULL,
            ambient_temp_c DECIMAL(4, 1) NULL,
            spin_thermal_power_w DECIMAL(6, 2) NULL COMMENT '自旋热电输出功率',
            spin_thermal_voltage_mv DECIMAL(6, 2) NULL COMMENT '自旋热电压',
            magnetic_x DECIMAL(7, 3) NULL,
            magnetic_y DECIMAL(7, 3) NULL,
            magnetic_z DECIMAL(7, 3) NULL,
            wind_speed_ms DECIMAL(4, 2) NULL,
            wind_direction_deg DECIMAL(5, 1) NULL,
            altitude_m DECIMAL(7, 2) NULL,
            pitch_deg DECIMAL(5, 2) NULL,
            yaw_deg DECIMAL(5, 2) NULL,
            roll_deg DECIMAL(5, 2) NULL,
            gps_lat DECIMAL(10, 6) NULL,
            gps_lng DECIMAL(10, 6) NULL,
            battery_soc_percent DECIMAL(5, 2) NULL,
            fault_code INT NULL DEFAULT 0,
            PRIMARY KEY (id, record_time),
            INDEX idx_flight_time (flight_id, record_time),
            INDEX idx_drone_time (drone_id, record_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        PARTITION BY RANGE (TO_DAYS(record_time)) (
            PARTITION p202601 VALUES LESS THAN (TO_DAYS('2026-02-01')),
            PARTITION p202602 VALUES LESS THAN (TO_DAYS('2026-03-01')),
            PARTITION p202603 VALUES LESS THAN (TO_DAYS('2026-04-01')),
            PARTITION p_future VALUES LESS THAN MAXVALUE
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sensor_snapshots")
    op.execute("DROP TABLE IF EXISTS flight_logs")
    op.drop_table("ai_decisions")
    op.drop_table("drones")
    op.drop_table("users")
