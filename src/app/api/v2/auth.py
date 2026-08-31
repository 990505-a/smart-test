"""Auth routes (用户模块): register / login / logout / me / password / user admin."""

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

async def get_current_user(
    db: DbSessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Require a valid Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    token = authorization.split(" ", 1)[1].strip()
    svc = AuthService(db)
    user = await svc.authenticate_token(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    return user


async def get_optional_user(
    db: DbSessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """Resolve the user when a token is present, else None (legacy routes)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    svc = AuthService(db)
    return await svc.authenticate_token(authorization.split(" ", 1)[1].strip())


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
async def logout(db: DbSessionDep, authorization: Annotated[str | None, Header()] = None):
    if authorization and authorization.lower().startswith("bearer "):
        svc = AuthService(db)
        await svc.logout(authorization.split(" ", 1)[1].strip())
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
