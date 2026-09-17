"""Auth routes (用户模块): login / me / password / user admin（登录页已移除，见下）。

平台 2026-09 去掉了登录：界面上没有登录/登出入口，`CurrentUserDep` 在无 token 时
返回内置本地用户。本路由保留给**外部脚本与验收测试**（它们仍可 /auth/login 拿 token
再带 X-Auth-Token 调用）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.app.api.deps import DbSessionDep
from src.app.db.models.user import User
from src.app.db.schemas.common import SuccessResponse
from src.app.services.auth_service import AuthService

router = APIRouter(prefix="/auth")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def _extract_token(authorization: str | None, x_auth_token: str | None) -> str | None:
    """Pull the platform token out of either supported header.

    `X-Auth-Token` is preferred and `Authorization: Bearer` remains supported.

    为什么要有这个自定义头：公网访问时平台前面还有一层 caddy Basic Auth
    （见 ~/h3services/Caddyfile），而 Basic 凭据同样走 `Authorization` 头——
    浏览器把 Basic 凭据自动带上、前端再显式设置 Bearer 会把它覆盖掉，
    结果反代 401。把应用 token 挪到独立头，两个鉴权层互不干扰；
    本机直连时两种头都能用，所以调用方不必区分环境。
    """
    if x_auth_token and x_auth_token.strip():
        return x_auth_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def get_current_user(
    db: DbSessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_auth_token: Annotated[str | None, Header()] = None,
) -> User:
    """解析当前用户——**本地单机模式，不需要登录**（2026-09 去掉登录页）。

    带有效 token 时仍按 token 解析（外部脚本 / 验收测试的登录路径保持可用），
    没有 token（或 token 失效）时返回内置的本地用户，而不是 401。

    这样做的原因：这是个单机内网工具，登录只增加摩擦，不带来隔离——所有请求
    本来就跑在同一台机器的同一个工作区里。需要外部调用时仍可用 /auth/login 拿
    token（tools/playwright-runner/acceptance 就是这么用的）。
    """
    token = _extract_token(authorization, x_auth_token)
    svc = AuthService(db)
    if token:
        user = await svc.authenticate_token(token)
        if user is not None:
            return user
    return await svc.local_user()


async def get_optional_user(
    db: DbSessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_auth_token: Annotated[str | None, Header()] = None,
) -> User | None:
    """Resolve the user when a token is present, else None (legacy routes)."""
    token = _extract_token(authorization, x_auth_token)
    if token is None:
        return None
    svc = AuthService(db)
    return await svc.authenticate_token(token)


CurrentUserDep = Annotated[User, Depends(get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = None
    role: str = "tester"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=200)


class ChangeUsernameRequest(BaseModel):
    new_username: str = Field(min_length=2, max_length=100)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=SuccessResponse, summary="Login")
async def login(data: LoginRequest, db: DbSessionDep):
    svc = AuthService(db)
    try:
        user, token = await svc.login(data.username, data.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    await db.commit()
    return SuccessResponse(success=True, data={"token": token, "user": _user_dict(user)})


@router.post("/logout", response_model=SuccessResponse, summary="Logout")
async def logout(db: DbSessionDep, authorization: Annotated[str | None, Header()] = None,
                 x_auth_token: Annotated[str | None, Header()] = None):
    if (token := _extract_token(authorization, x_auth_token)) is not None:
        svc = AuthService(db)
        await svc.logout(token)
        await db.commit()
    return SuccessResponse(success=True, data={"logged_out": True})


@router.get("/me", response_model=SuccessResponse, summary="Current user")
async def me(user: CurrentUserDep):
    return SuccessResponse(success=True, data=_user_dict(user))


@router.post("/change-password", response_model=SuccessResponse, summary="Change own password")
async def change_password(data: ChangePasswordRequest, user: CurrentUserDep, db: DbSessionDep):
    svc = AuthService(db)
    try:
        await svc.change_password(user, data.old_password, data.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return SuccessResponse(success=True, data={"changed": True})


@router.post("/change-username", response_model=SuccessResponse, summary="Change own username")
async def change_username(data: ChangeUsernameRequest, user: CurrentUserDep, db: DbSessionDep):
    svc = AuthService(db)
    try:
        await svc.change_username(user, data.new_username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return SuccessResponse(success=True, data=_user_dict(user))


@router.get("/users", response_model=SuccessResponse, summary="List users (admin)")
async def list_users(user: CurrentUserDep, db: DbSessionDep):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    svc = AuthService(db)
    users = await svc.list_users()
    return SuccessResponse(success=True, data=[_user_dict(u) for u in users])


@router.post("/users", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED,
             summary="Create user (admin)")
async def create_user(data: RegisterRequest, user: CurrentUserDep, db: DbSessionDep):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    svc = AuthService(db)
    try:
        new_user = await svc.create_user(data.username, data.password, data.display_name, data.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return SuccessResponse(success=True, data=_user_dict(new_user))
