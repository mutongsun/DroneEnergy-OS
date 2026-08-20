"""数据库引擎与会话工厂

- pool_pre_ping：防 MySQL 8 小时空闲断连（wait_timeout）后拿到死连接
- pool_size=10 + max_overflow=20：单副本演示规模绰绰有余
- instrument_engine：连接池借出/归还接入 db_pool_in_use 指标
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.monitoring.metrics import instrument_engine

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
instrument_engine(engine)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级会话，用毕归还连接池"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
