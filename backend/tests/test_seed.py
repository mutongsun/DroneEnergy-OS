"""种子数据测试：幂等性 + 默认账号/无人机完整性

seed() 直接使用 app.db.SessionLocal（生产库会话工厂），
测试中 monkeypatch 替换为内存库会话工厂，避免触碰真实数据库。
"""

from collections.abc import Generator

import pytest
from sqlalchemy import select

import app.auth.seed as seed_mod
from app.auth.seed import DEFAULT_DRONES, DEFAULT_USERS, seed
from app.models import Drone, User


@pytest.fixture
def seed_session(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """把 seed 的会话工厂指到测试内存库"""
    from tests.conftest import TestingSessionLocal

    monkeypatch.setattr(seed_mod, "SessionLocal", TestingSessionLocal)
    yield


def test_seed_creates_defaults(seed_session: None) -> None:
    seed()

    from tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        users = {u.username: u.role for u in db.scalars(select(User)).all()}
        drones = {d.id: d.name for d in db.scalars(select(Drone)).all()}

    assert users == {username: role for username, _, role in DEFAULT_USERS}
    assert drones == {drone_id: name for drone_id, name, _, _ in DEFAULT_DRONES}


def test_seed_is_idempotent(seed_session: None) -> None:
    """重复执行不重复插入、不覆盖已有记录"""
    seed()
    seed()

    from tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        user_count = len(db.scalars(select(User)).all())
        drone_count = len(db.scalars(select(Drone)).all())

    assert user_count == len(DEFAULT_USERS)
    assert drone_count == len(DEFAULT_DRONES)


def test_seed_does_not_overwrite_existing(seed_session: None) -> None:
    """已存在记录跳过：预置一个改过名的无人机，seed 后应保留"""
    from tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        db.add(Drone(id=1, name="已被接管", model="Custom", status="idle", max_battery_mah=1))
        db.commit()

    seed()

    with TestingSessionLocal() as db:
        drone = db.get(Drone, 1)
        assert drone is not None
        assert drone.name == "已被接管"
