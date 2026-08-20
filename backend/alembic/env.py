"""Alembic 迁移环境

连接串优先读环境变量 DATABASE_URL，凭据不进版本库。
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL", "mysql+pymysql://root:root123@localhost:3306/drone_energy")
# ConfigParser 会对 % 做插值，连接串中的 % 必须转义
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL，不连接数据库"""
    context.configure(
        url=db_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行迁移"""
    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
