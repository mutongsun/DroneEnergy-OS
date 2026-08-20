"""演示数据种子（幂等）：默认账号 + 演示无人机

生产实践注记：真实系统应通过受控 CLI/初始化任务注入账号并强制首次改密，
此处为演示便利保留默认口令（仅本地 compose 环境）。
"""

import logging

from sqlalchemy import select

from app.auth.security import hash_password
from app.db import SessionLocal
from app.models import Drone, User

logger = logging.getLogger(__name__)

DEFAULT_USERS: tuple[tuple[str, str, str], ...] = (
    ("admin", "admin123", "admin"),
    ("operator", "operator123", "operator"),
    ("viewer", "viewer123", "viewer"),
)

# 与 fake_data_generator 模拟器的 drone_id 1/2/3 一一对应
DEFAULT_DRONES: tuple[tuple[int, str, str, int], ...] = (
    (1, "演示无人机-1", "DJI_Mavic3", 5000),
    (2, "演示无人机-2", "XAG_P80Pro", 12000),
    (3, "演示无人机-3", "DJI_Mavic3", 5000),
)


def seed() -> None:
    """已存在的记录跳过，不做任何覆盖"""
    with SessionLocal() as db:
        for username, password, role in DEFAULT_USERS:
            if db.scalar(select(User).where(User.username == username)) is None:
                db.add(User(username=username, password_hash=hash_password(password), role=role))
                logger.info("seeded user %s (role=%s)", username, role)
        for drone_id, name, model, mah in DEFAULT_DRONES:
            if db.get(Drone, drone_id) is None:
                db.add(
                    Drone(id=drone_id, name=name, model=model, status="flying", max_battery_mah=mah)
                )
                logger.info("seeded drone %s (model=%s)", name, model)
        db.commit()


if __name__ == "__main__":
    from app.monitoring.logging import setup_logging

    setup_logging()
    seed()
