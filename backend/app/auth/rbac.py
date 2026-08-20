"""RBAC：基于角色的端点访问控制（FastAPI 依赖工厂）

惯例：admin 角色隐式拥有全部权限，无需在各端点逐一枚举。
用法：`Depends(require_roles("operator", "admin"))`
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException

from app.dependencies import get_current_user
from app.models import User


def require_roles(*roles: str) -> Callable[[User], User]:
    allowed = frozenset(roles)

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role == "admin" or user.role in allowed:
            return user
        raise HTTPException(status_code=403, detail=f"需要以下角色之一：{sorted(allowed)}")

    return checker
