"""公共依赖：JWT Bearer 解析 → 当前用户"""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """解析 Authorization: Bearer <jwt> 并加载用户；任何失败统一 401"""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="缺少 Bearer 凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
        sub = payload["sub"]
        if not isinstance(sub, str):
            raise ValueError("sub claim 必须为字符串")  # noqa: TRY301 — 统一走 401
        user_id = int(sub)
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user
