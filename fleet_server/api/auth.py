"""Auth dependencies + login endpoint (SRP).

Tokens are accepted either as Bearer headers (used by the dashboard's
fetch calls) or as a secure `mdm_session` cookie (used for SSO from
/grafana/ via nginx auth_request).

get_current_user  — extracts user from JWT (header OR cookie).
require_role      — factory returning a dependency for role-based access.
require_auth      — any authenticated user, used by /verify.
"""

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import (
    APIKeyCookie,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pydantic import BaseModel
from sqlalchemy import func, select
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
    # Accepts either an email (admin@tetradapt.com) or a short
    # user_id (admin). Field is called `email` for backwards compat
    # with existing clients; the server resolves either form.
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


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class PasswordResetResponse(BaseModel):
    id: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


MIN_PASSWORD_LENGTH = 8


VALID_ROLES = {"admin", "operator", "viewer"}


def _generate_password(length: int = 16) -> str:
    """URL-safe random password — letters, digits, dashes, underscores."""
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def _count_active_admins(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", User.is_active == True)  # noqa: E712
    )
    return int(result.scalar_one())


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
    # Look up by email first, then fall back to user_id (so "admin"
    # works just as well as "admin@tetradapt.com").
    identifier = payload.email.strip()
    result = await db.execute(
        select(User).where((User.email == identifier) | (User.id == identifier))
    )
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
    # Nuke everything the browser has stored for this origin: cookies
    # (incl. Grafana's own session), localStorage, cached responses.
    # Ensures no stale authed page survives the sign-out.
    response.headers["Clear-Site-Data"] = '"cookies", "storage", "cache"'
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


@router.post("/me/password")
async def change_my_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
):
    """Change your own password. Requires the current password."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if len(payload.new_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"New password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    if payload.new_password == payload.current_password:
        raise HTTPException(
            status_code=400, detail="New password must differ from current password"
        )

    user.hashed_password = hash_password(payload.new_password)
    await db.commit()

    audit = AuditService(db, user_id=user.id)
    await audit.log("change_password", "user", {"self": True})

    return {"ok": True}


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """List all users — admin only."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Update role and/or is_active — admin only.

    Guards:
      - Cannot demote or deactivate yourself (lockout protection).
      - Cannot leave the system with zero active admins.
    """
    if payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=400, detail="Nothing to update")

    if payload.role is not None and payload.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {sorted(VALID_ROLES)}",
        )

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role or active status",
        )

    new_role = payload.role if payload.role is not None else target.role
    new_active = payload.is_active if payload.is_active is not None else target.is_active

    would_lose_last_admin = (
        target.role == "admin"
        and target.is_active
        and (new_role != "admin" or not new_active)
    )
    if would_lose_last_admin and await _count_active_admins(db) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot leave the system without at least one active admin",
        )

    changes: dict = {}
    if payload.role is not None and payload.role != target.role:
        changes["role"] = {"from": target.role, "to": payload.role}
        target.role = payload.role
    if payload.is_active is not None and payload.is_active != target.is_active:
        changes["is_active"] = {"from": target.is_active, "to": payload.is_active}
        target.is_active = payload.is_active

    await db.commit()
    await db.refresh(target)

    if changes:
        audit = AuditService(db, user_id=admin.id)
        await audit.log("update", "user", {"target_user": target.id, **changes})

    return target


@router.post(
    "/users/{user_id}/reset-password", response_model=PasswordResetResponse
)
async def reset_user_password(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Generate a new password for the user — admin only.

    Returns the plaintext password ONCE. Surface it in the UI immediately
    and never store it; bcrypt hash is what lands in the DB.
    """
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    new_pw = _generate_password()
    target.hashed_password = hash_password(new_pw)
    await db.commit()

    audit = AuditService(db, user_id=admin.id)
    await audit.log("reset_password", "user", {"target_user": target.id})

    return PasswordResetResponse(id=target.id, password=new_pw)
