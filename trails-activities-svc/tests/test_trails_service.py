from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

# Ensure configuration is in place before importing the app
if "DATABASE_URL" not in os.environ:
    fd, path = tempfile.mkstemp(prefix="trails_test_", suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{path}"

os.environ.setdefault("AUTH_JWKS_URL", "http://localhost/jwks.json")
os.environ.setdefault("INVITE_SECRET", "test-secret")
os.environ.setdefault("INVITE_BASE_URL", "http://test.local/invites")
os.environ.setdefault("TOKEN_ISSUER", "test-issuer")

from app.main import app  # noqa: E402
from app.deps import get_claims  # noqa: E402
from app.db import async_session_maker, engine  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Registration,
    RegStatus,
)


def override_claims(payload: dict):
    async def _override():
        return payload

    return _override


@pytest.fixture(autouse=True)
async def reset_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.anyio
async def test_create_trail_respects_initial_status():
    org_id = uuid4()
    app.dependency_overrides[get_claims] = override_claims(
        {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(org_id)]}
    )
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            now = datetime.now(timezone.utc)
            payload = {
                "title": "Morning Walk",
                "description": " gentle warm-up ",
                "starts_at": (now + timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=2)).isoformat(),
                "capacity": 25,
                "location": "Community Park",
                "status": "draft",
            }
            response = await client.post(f"/trails/orgs/{org_id}", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["title"] == "Morning Walk"
    finally:
        app.dependency_overrides.pop(get_claims, None)


@pytest.mark.anyio
async def test_list_trails_rejects_unaffiliated_organiser():
    org_id = uuid4()
    other_org_id = uuid4()
    # Seed a trail directly
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        app.dependency_overrides[get_claims] = override_claims(
            {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(org_id)]}
        )
        try:
            now = datetime.now(timezone.utc)
            payload = {
                "title": "Gentle Yoga",
                "starts_at": (now + timedelta(hours=1)).isoformat(),
                "ends_at": (now + timedelta(hours=2)).isoformat(),
                "capacity": 30,
            }
            response = await client.post(f"/trails/orgs/{org_id}", json=payload)
            assert response.status_code == 201
        finally:
            app.dependency_overrides.pop(get_claims, None)

    # Attempt to query with organiser not in the organisation
    app.dependency_overrides[get_claims] = override_claims(
        {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(other_org_id)]}
    )
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            response = await client.get(f"/trails?org_id={org_id}")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_claims, None)


@pytest.mark.anyio
async def test_list_attendees_pagination():
    org_id = uuid4()
    app.dependency_overrides[get_claims] = override_claims(
        {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(org_id)]}
    )
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            now = datetime.now(timezone.utc)
            resp = await client.post(
                f"/trails/orgs/{org_id}",
                json={
                    "title": "Trail with roster",
                    "starts_at": (now + timedelta(hours=1)).isoformat(),
                    "ends_at": (now + timedelta(hours=3)).isoformat(),
                    "capacity": 100,
                },
            )
        assert resp.status_code == 201
        trail_id = UUID(resp.json()["id"])

        # Seed registrations
        async with async_session_maker() as session:
            session.add_all(
                [
                    Registration(
                        trail_id=trail_id,
                        user_id=uuid4(),
                        org_id=org_id,
                        status=RegStatus.CONFIRMED,
                    )
                    for _ in range(30)
                ]
            )
            await session.commit()

        async with AsyncClient(app=app, base_url="http://testserver") as client:
            first_page = await client.get(
                f"/trails/{trail_id}/attendees", params={"limit": 10, "offset": 0}
            )
            assert first_page.status_code == 200
            page_data = first_page.json()
            assert page_data["total"] == 30
            assert page_data["limit"] == 10
            assert page_data["offset"] == 0
            assert page_data["has_more"] is True
            assert len(page_data["items"]) == 10

            third_page = await client.get(
                f"/trails/{trail_id}/attendees", params={"limit": 10, "offset": 20}
            )
            assert third_page.status_code == 200
            page_three = third_page.json()
            assert page_three["has_more"] is False
            assert len(page_three["items"]) == 10
    finally:
        app.dependency_overrides.pop(get_claims, None)
