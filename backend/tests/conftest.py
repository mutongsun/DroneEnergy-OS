"""测试夹具：SQLite 内存库 + get_db 依赖覆盖 + TestClient

设计要点：
- StaticPool 共享同一内存库：端点写入端与测试断言端看到同一份数据
- BigIntPK（with_variant）使模型在 SQLite 下可用自增主键
- TestClient 不用 with：跳过 lifespan，HTTP 测试不依赖 Redis
"""

from collections.abc import Callable, Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import hash_password
from app.dependencies import get_db
from app.main import app
from app.models import Base, User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _fresh_schema():
    """每个测试独立建表/清表，互不污染"""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def create_user() -> Callable[[str, str, str], None]:
    def _create(username: str, password: str, role: str) -> None:
        with TestingSessionLocal() as db:
            db.add(User(username=username, password_hash=hash_password(password), role=role))
            db.commit()

    return _create


@pytest.fixture
def login(client: TestClient, create_user: Callable[..., None]) -> Callable[..., dict[str, str]]:
    """返回 (username, password, role) → Authorization 请求头"""

    def _login(username: str, password: str, role: str = "operator") -> dict[str, str]:
        create_user(username, password, role)
        resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        token: str = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _login


@pytest.fixture
def frame_factory() -> Callable[..., dict[str, Any]]:
    """构造与模拟器字段一致的单帧数据"""

    def _frame(**overrides: Any) -> dict[str, Any]:
        from datetime import UTC, datetime

        base: dict[str, Any] = {
            "type": "sensor_frame",  # 链路字段，应被 extra="ignore" 丢弃
            "drone_id": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "voltage_v": 22.1,
            "current_a": 12.5,
            "battery_soc_percent": 88.5,
            "spin_thermal_power_w": 12.3,
            "gps_lat": 39.9042,
            "gps_lng": 116.4074,
            "fault_code": 0,
        }
        base.update(overrides)
        return base

    return _frame
