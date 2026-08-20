"""演示账号种子（幂等）：仅创建缺失的默认用户

生产实践注记：真实系统应通过受控 CLI/初始化任务注入账号并强制首次改密，
此处为演示便利保留默认口令（仅本地 compose 环境）。
"""

import logging

from sqlalchemy import select

from app.auth.security import hash_password
from app.db import SessionLocal
from app.models import User

logger = logging.getLogger(__name__)

DEFAULT_USERS: tuple[tuple[str, str, str], ...] = (
    ("admin", "admin123", "admin"),
    ("operator", "operator123", "operator"),
    ("viewer", "viewer123", "viewer"),
)


def seed() -> None:
    """已存在的用户跳过，不做任何覆盖"""
    with SessionLocal() as db:
        for username, password, role in DEFAULT_USERS:
            if db.scalar(select(User).where(User.username == username)) is None:
                db.add(User(username=username, password_hash=hash_password(password), role=role))
                logger.info("seeded user %s (role=%s)", username, role)
        db.commit()


if __name__ == "__main__":
    from app.monitoring.logging import setup_logging

    setup_logging()
    seed()
