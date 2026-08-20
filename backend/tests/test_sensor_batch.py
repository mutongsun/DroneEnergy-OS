"""传感器批量上报端点测试：认证、RBAC、校验、落库"""

from datetime import datetime

from sqlalchemy import func, select

from app.models import SensorSnapshot
from tests.conftest import TestingSessionLocal


def _post_batch(client, frames, headers=None):
    return client.post("/api/v1/sensor/batch", json={"frames": frames}, headers=headers)


def test_batch_accepted_and_persisted(client, login, frame_factory):
    headers = login("op", "op123")
    resp = _post_batch(client, [frame_factory(), frame_factory(drone_id=2)], headers)
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 2}

    with TestingSessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(SensorSnapshot))
        assert count == 2
        soc_values = db.scalars(select(SensorSnapshot.battery_soc_percent)).all()
        assert soc_values == [88.5, 88.5]


def test_batch_drops_link_fields(client, login, frame_factory):
    """type 等链路字段应被忽略，不参与落库"""
    headers = login("op", "op123")
    resp = _post_batch(client, [frame_factory()], headers)
    assert resp.status_code == 200
    with TestingSessionLocal() as db:
        row = db.scalar(select(SensorSnapshot))
        assert row is not None
        assert not hasattr(row, "type")


def test_batch_requires_auth(client, frame_factory):
    assert _post_batch(client, [frame_factory()]).status_code == 401


def test_batch_viewer_forbidden(client, login, frame_factory):
    headers = login("viewer", "v123", role="viewer")
    assert _post_batch(client, [frame_factory()], headers).status_code == 403


def test_batch_admin_bypass(client, login, frame_factory):
    """admin 隐式拥有全部权限（RBAC 惯例）"""
    headers = login("root", "r123", role="admin")
    assert _post_batch(client, [frame_factory()], headers).status_code == 200


def test_batch_empty_rejected(client, login):
    headers = login("op", "op123")
    assert _post_batch(client, [], headers).status_code == 422


def test_batch_over_limit_rejected(client, login, frame_factory):
    """超过 100 帧/批的请求应被契约层拒绝"""
    headers = login("op", "op123")
    assert _post_batch(client, [frame_factory() for _ in range(101)], headers).status_code == 422


def test_batch_timestamp_normalized_to_utc_naive(client, login, frame_factory):
    """带时区的 timestamp 必须归一化为 UTC naive 再入库（MySQL DATETIME 无时区）"""
    headers = login("op", "op123")
    resp = _post_batch(client, [frame_factory(timestamp="2026-08-20T12:00:00+08:00")], headers)
    assert resp.status_code == 200
    with TestingSessionLocal() as db:
        row = db.scalar(select(SensorSnapshot))
        assert row is not None
        assert row.record_time == datetime(2026, 8, 20, 4, 0, 0)


def test_batch_flight_id_optional(client, login, frame_factory):
    """flight_id 缺省可空（迁移 0002）：数据先于飞行记录落库"""
    headers = login("op", "op123")
    resp = _post_batch(client, [frame_factory()], headers)
    assert resp.status_code == 200
    with TestingSessionLocal() as db:
        row = db.scalar(select(SensorSnapshot))
        assert row is not None
        assert row.flight_id is None
