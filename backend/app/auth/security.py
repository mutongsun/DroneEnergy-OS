"""口令哈希（bcrypt）与 JWT 签发/校验（PyJWT, HS256）

选型说明：
- bcrypt 自适应慢哈希，工业界口令存储事实标准
- PyJWT 轻量且持续维护（python-jose 已有安全通告历史，不采用）
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        # 哈希串格式非法（脏数据/伪造值）一律视为校验失败，不抛异常
        return False


def create_access_token(user_id: int, role: str) -> str:
    """签发访问令牌；claims: sub(用户ID)/role/iat/exp"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    """校验签名与有效期；失败抛 jwt.PyJWTError 子类"""
    decoded: dict[str, object] = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    return decoded
