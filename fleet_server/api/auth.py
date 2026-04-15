"""Auth dependencies + login endpoint (SRP).

get_current_user — extracts user from JWT Bearer token.
require_role — factory that returns a dependency for role-based access.
These are FastAPI Depends — injected into route handlers (DIP).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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
security = HTTPBearer(auto_error=False)


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

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Extract user from JWT Bearer token. Returns None if no token (public access)."""
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
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


def require_role(*roles: str):
    """Factory that returns a dependency requiring specific role(s).

    Usage: Depends(require_role("admin", "operator"))
    Follows OCP — add new roles without changing existing guards.
    """
    async def _guard(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        payload = decode_token(credentials.credentials)
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

@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
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

    # Audit
    audit = AuditService(db, user_id=user.id)
    await audit.log("login", "user", {"email": user.email})

    return TokenResponse(
        access_token=token, role=user.role, user_id=user.id,
    )


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
