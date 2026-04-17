"""Auth dependencies + login endpoint (SRP).

Tokens are accepted either as Bearer headers (used by the dashboard's
fetch calls) or as a secure `mdm_session` cookie (used for SSO from
/grafana/ via nginx auth_request).

get_current_user  — extracts user from JWT (header OR cookie).
require_role      — factory returning a dependency for role-based access.
require_auth      — any authenticated user, used by /verify.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import (
    APIKeyCookie,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import get_db
from fleet_server.models.user import User
from fleet_server.services.audit import AuditService
from fleet_server.services.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter()

COOKIE_NAME = "mdm_session"
COOKIE_MAX_AGE = 60 * 60 * 24  # 24h, matches JWT exp

_bearer = HTTPBearer(auto_error=False)
_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False)


# ─── Schemas ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class UserCreate(BaseModel):
    id: str
    email: str
    password: str
    role: str = "viewer"


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


# ─── Dependencies ───────────────────────────────────────────────────


def _extract_token(
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer),
    cookie: str | None = Depends(_cookie),
) -> str | None:
    """Prefer Authorization: Bearer, fall back to mdm_session cookie."""
    if bearer and bearer.credentials:
        return bearer.credentials
    return cookie


async def get_current_user(
    token: str | None = Depends(_extract_token),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Extract user from JWT. Returns None if no token (public access)."""
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def require_auth(user: User | None = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_role(*roles: str):
    """Dependency factory — user must have one of the given roles.

    Follows OCP — add new roles without changing existing guards.
    """

    async def _guard(
        token: str | None = Depends(_extract_token),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        payload = decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        user_id = payload.get("sub")
        user_role = payload.get("role")

        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not authorized. Required: {roles}",
            )

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user

    return _guard


# ─── Endpoints ──────────────────────────────────────────────────────


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    token = create_access_token(user.id, user.role)
    _set_session_cookie(response, token)

    audit = AuditService(db, user_id=user.id)
    await audit.log("login", "user", {"email": user.email})

    return TokenResponse(access_token=token, role=user.role, user_id=user.id)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/verify")
async def verify(response: Response, user: User = Depends(require_auth)):
    """nginx auth_request target. On success, returns X-Auth-* response
    headers that nginx propagates into upstream requests (e.g. as
    X-WEBAUTH-USER for Grafana's auth.proxy mode).
    """
    response.headers["X-Auth-User"] = user.email
    response.headers["X-Auth-Role"] = user.role
    response.headers["X-Auth-Id"] = user.id
    return {"user": user.id, "role": user.role}


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Create a new user — admin only."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=payload.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    audit = AuditService(db, user_id=_admin.id)
    await audit.log("create", "user", {"new_user": user.id, "role": user.role})

    return user


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(require_role("admin", "operator", "viewer"))):
    return user
