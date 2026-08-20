"""JWT 认证端点测试：登录、/me、令牌校验"""


def test_login_success(client, create_user):
    create_user("op", "op123", "operator")
    resp = client.post("/api/v1/auth/login", json={"username": "op", "password": "op123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "operator"
    assert body["username"] == "op"
    assert body["access_token"]


def test_login_wrong_password(client, create_user):
    create_user("op", "op123", "operator")
    resp = client.post("/api/v1/auth/login", json={"username": "op", "password": "bad"})
    assert resp.status_code == 401


def test_login_unknown_user_same_error(client, create_user):
    """未知用户与密码错误返回相同信息，防用户名枚举"""
    create_user("op", "op123", "operator")
    wrong_pw = client.post("/api/v1/auth/login", json={"username": "op", "password": "bad"})
    unknown = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "bad"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_valid_token(client, login):
    headers = login("op", "op123")
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "op"
    assert body["role"] == "operator"


def test_me_with_garbage_token(client):
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_me_with_expired_token(client, create_user):
    """过期令牌必须被拒绝（exp 校验）"""
    from datetime import UTC, datetime

    import jwt

    from app.config import settings

    create_user("op", "op123", "operator")
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": "1",
            "role": "operator",
            "iat": int(now.timestamp()) - 7200,
            "exp": int(now.timestamp()) - 3600,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
