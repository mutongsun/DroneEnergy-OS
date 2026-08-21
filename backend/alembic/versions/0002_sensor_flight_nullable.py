"""sensor_snapshots.flight_id 改为可空

背景：传感器数据可能先于飞行记录产生（飞行生命周期由 flights 模块管理，
尚未交付），NOT NULL 约束会让无关联飞行的数据上报直接失败。

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sensor_snapshots",
        "flight_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )


def downgrade() -> None:
    # 回滚前必须清理 NULL 行，否则 NOT NULL 约束会失败（有数据损失，慎用）
    op.execute("DELETE FROM sensor_snapshots WHERE flight_id IS NULL")
    op.alter_column(
        "sensor_snapshots",
        "flight_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
