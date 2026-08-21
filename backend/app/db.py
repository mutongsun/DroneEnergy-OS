"""数据库引擎与会话工厂

- pool_pre_ping：防 MySQL 8 小时空闲断连（wait_timeout）后拿到死连接
- pool_size=30 + max_overflow=30：压测修正（v3）。原 10+20 在 ~40 并发
  下触发 QueuePool 30s 超时级联（p50 延迟 31s、7% 500 错误）；
  上限 60 仍远低于 MySQL 默认 max_connections=151
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
    pool_size=30,
    max_overflow=30,
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
