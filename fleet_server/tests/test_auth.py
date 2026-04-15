"""Auth tests — JWT login, role-based access, token validation."""

import pytest

from fleet_server.models.user import User
from fleet_server.services.auth import create_access_token, hash_password


async def _create_user(db, user_id="admin", email="admin@test.com", role="admin"):
    user = User(
        id=user_id,
        email=email,
        hashed_password=hash_password("password123"),
        role=role,
    )
    db.add(user)
    await db.commit()
    return user


def _auth_header(user_id: str, role: str) -> dict:
    token = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


# ─── Login ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(client, db_session):
    await _create_user(db_session)
    resp = await client.post("/api/auth/login", json={
        "email": "admin@test.com", "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    assert data["user_id"] == "admin"
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client, db_session):
    await _create_user(db_session)
    resp = await client.post("/api/auth/login", json={
        "email": "admin@test.com", "password": "wrong",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    resp = await client.post("/api/auth/login", json={
        "email": "ghost@test.com", "password": "anything",
    })
    assert resp.status_code == 401


# ─── Token Validation ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_with_valid_token(client, db_session):
    await _create_user(db_session)
    resp = await client.get(
        "/api/auth/me", headers=_auth_header("admin", "admin")
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "admin"
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_me_without_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_invalid_token(client):
    resp = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )
    assert resp.status_code == 401


# ─── Role-Based Access ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user_as_admin(client, db_session):
    await _create_user(db_session)
    resp = await client.post(
        "/api/auth/users",
        json={"id": "new-op", "email": "op@test.com", "password": "pass", "role": "operator"},
        headers=_auth_header("admin", "admin"),
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "operator"


@pytest.mark.asyncio
async def test_create_user_as_operator_forbidden(client, db_session):
    await _create_user(db_session, user_id="op1", email="op1@test.com", role="operator")
    resp = await client.post(
        "/api/auth/users",
        json={"id": "new", "email": "new@test.com", "password": "pass"},
        headers=_auth_header("op1", "operator"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user_as_viewer_forbidden(client, db_session):
    await _create_user(db_session, user_id="v1", email="v1@test.com", role="viewer")
    resp = await client.post(
        "/api/auth/users",
        json={"id": "new", "email": "new@test.com", "password": "pass"},
        headers=_auth_header("v1", "viewer"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client, db_session):
    await _create_user(db_session)
    resp = await client.post(
        "/api/auth/users",
        json={"id": "dup", "email": "admin@test.com", "password": "pass"},
        headers=_auth_header("admin", "admin"),
    )
    assert resp.status_code == 409


# ─── Protected Routes (devices as example) ─────────────────────────

@pytest.mark.asyncio
async def test_device_crud_works_without_auth(client):
    """For now, device CRUD is open — auth is opt-in per route.
    This test confirms existing behavior is preserved."""
    resp = await client.get("/api/devices/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_audit_log_created_on_device_create(client, db_session):
    """Verify audit entry is created when a device is added."""
    from sqlalchemy import select
    from fleet_server.models.audit_log import AuditLog

    await client.post("/api/devices/", json={
        "device_id": "audit-test", "mac": "AU:DI:TT:ES:T0:01",
        "firmware_version": "1.0.0",
    })

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.resource == "device")
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.action == "create"
    assert audit.details["device_id"] == "audit-test"
