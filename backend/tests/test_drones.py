"""设备 CRUD 端点测试：分页、筛选、RBAC、404、部分更新"""


def _create(client, headers, name="Mavic-01", model="DJI_Mavic3", **overrides):
    body = {"name": name, "model": model, **overrides}
    resp = client.post("/api/v1/drones", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_drones(client, headers, count=5):
    """创建 count 台设备：奇数 idle，偶数 flying，交替两种机型"""
    for i in range(1, count + 1):
        _create(
            client,
            headers,
            name=f"drone-{i:02d}",
            model="DJI_Mavic3" if i % 2 else "XAG_P80Pro",
            status="idle" if i % 2 else "flying",
        )


# ---------- 读权限：三种角色都可读 ----------


def test_list_requires_auth(client):
    assert client.get("/api/v1/drones").status_code == 401


def test_list_viewer_can_read(client, login):
    headers = login("viewer", "v123", role="viewer")
    assert client.get("/api/v1/drones", headers=headers).status_code == 200


# ---------- 创建 ----------


def test_create_operator(client, login):
    headers = login("op", "op123")
    drone = _create(client, headers, name="Mavic-01", model="DJI_Mavic3")
    assert drone["id"] > 0
    assert drone["status"] == "idle"
    assert drone["max_battery_mah"] == 5000


def test_create_viewer_forbidden(client, login):
    headers = login("viewer", "v123", role="viewer")
    resp = client.post("/api/v1/drones", json={"name": "x", "model": "y"}, headers=headers)
    assert resp.status_code == 403


def test_create_rejects_invalid_status(client, login):
    headers = login("op", "op123")
    resp = client.post(
        "/api/v1/drones", json={"name": "x", "model": "y", "status": "broken"}, headers=headers
    )
    assert resp.status_code == 422


def test_create_rejects_bad_battery(client, login):
    headers = login("op", "op123")
    resp = client.post(
        "/api/v1/drones", json={"name": "x", "model": "y", "max_battery_mah": -1}, headers=headers
    )
    assert resp.status_code == 422


# ---------- 分页 ----------


def test_pagination_metadata(client, login):
    headers = login("op", "op123")
    _seed_drones(client, headers, count=5)

    resp = client.get("/api/v1/drones?page=2&page_size=2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert len(body["items"]) == 2
    # id 倒序：新创建的在前
    ids = [d["id"] for d in body["items"]]
    assert ids == sorted(ids, reverse=True)


def test_last_page_partial(client, login):
    headers = login("op", "op123")
    _seed_drones(client, headers, count=5)
    body = client.get("/api/v1/drones?page=3&page_size=2", headers=headers).json()
    assert len(body["items"]) == 1  # 5 条数据第 3 页只剩 1 条


def test_page_size_capped_at_100(client, login):
    headers = login("op", "op123")
    resp = client.get("/api/v1/drones?page_size=101", headers=headers)
    assert resp.status_code == 422


def test_page_zero_rejected(client, login):
    headers = login("op", "op123")
    assert client.get("/api/v1/drones?page=0", headers=headers).status_code == 422


# ---------- 筛选 ----------


def test_filter_by_status(client, login):
    headers = login("op", "op123")
    _seed_drones(client, headers, count=4)
    body = client.get("/api/v1/drones?status=flying", headers=headers).json()
    assert body["total"] == 2
    assert all(d["status"] == "flying" for d in body["items"])


def test_filter_by_model(client, login):
    headers = login("op", "op123")
    _seed_drones(client, headers, count=4)
    body = client.get("/api/v1/drones?model=XAG_P80Pro", headers=headers).json()
    assert body["total"] == 2
    assert all(d["model"] == "XAG_P80Pro" for d in body["items"])


def test_filter_combined(client, login):
    """status + model 组合过滤取交集"""
    headers = login("op", "op123")
    _seed_drones(client, headers, count=4)
    body = client.get("/api/v1/drones?status=idle&model=XAG_P80Pro", headers=headers).json()
    # 奇数号 idle+Mavic，偶数号 flying+P80 → 交集为空
    assert body["total"] == 0
    assert body["items"] == []


def test_filter_empty_result_ok(client, login):
    headers = login("op", "op123")
    body = client.get("/api/v1/drones?status=offline", headers=headers).json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 10}


# ---------- 详情 / 更新 / 删除 ----------


def test_get_by_id_and_404(client, login):
    headers = login("op", "op123")
    drone = _create(client, headers)
    ok = client.get(f"/api/v1/drones/{drone['id']}", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["name"] == drone["name"]
    assert client.get("/api/v1/drones/99999", headers=headers).status_code == 404


def test_patch_partial_update(client, login):
    """只传 status：其余字段保持不变"""
    headers = login("op", "op123")
    drone = _create(client, headers, name="A", model="DJI_Mavic3")
    resp = client.patch(f"/api/v1/drones/{drone['id']}", json={"status": "flying"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "flying"
    assert body["name"] == "A"  # 未更新的字段不受影响
    assert body["max_battery_mah"] == 5000


def test_patch_404(client, login):
    headers = login("op", "op123")
    resp = client.patch("/api/v1/drones/99999", json={"status": "idle"}, headers=headers)
    assert resp.status_code == 404


def test_delete_then_404(client, login):
    headers = login("op", "op123")
    drone = _create(client, headers)
    assert client.delete(f"/api/v1/drones/{drone['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/drones/{drone['id']}", headers=headers).status_code == 404
    # 重复删除 → 404（幂等删除语义）
    assert client.delete(f"/api/v1/drones/{drone['id']}", headers=headers).status_code == 404


def test_delete_viewer_forbidden(client, login):
    op_headers = login("op", "op123")
    drone = _create(client, op_headers)
    viewer_headers = login("viewer", "v123", role="viewer")
    resp = client.delete(f"/api/v1/drones/{drone['id']}", headers=viewer_headers)
    assert resp.status_code == 403
