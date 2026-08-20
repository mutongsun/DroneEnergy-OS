"""认证端点：登录换发 JWT、查询当前用户"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest, TokenResponse, UserOut
from app.auth.security import create_access_token, verify_password
from app.db import get_db
from app.dependencies import get_current_user
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == body.username))
    # 统一错误信息，避免暴露"用户是否存在"（防用户名枚举）
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
