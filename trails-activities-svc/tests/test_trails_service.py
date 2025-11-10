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


@pytest.mark.anyio
async def test_activity_crud_and_ordering():
    org_id = uuid4()
    app.dependency_overrides[get_claims] = override_claims(
        {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(org_id)]}
    )
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            now = datetime.now(timezone.utc)
            create_trail_resp = await client.post(
                f"/trails/orgs/{org_id}",
                json={
                    "title": "Forest Walk",
                    "starts_at": (now + timedelta(hours=1)).isoformat(),
                    "ends_at": (now + timedelta(hours=2)).isoformat(),
                    "capacity": 40,
                },
            )
            assert create_trail_resp.status_code == 201
            trail_id = create_trail_resp.json()["id"]

            first = await client.post(
                f"/trails/{trail_id}/activities",
                json={"title": "Warm up", "points": 5},
            )
            assert first.status_code == 201
            first_payload = first.json()
            assert first_payload["order"] == 1

            second = await client.post(
                f"/trails/{trail_id}/activities",
                json={"title": "Scenic loop", "points": 10, "order": 1},
            )
            assert second.status_code == 201
            second_payload = second.json()
            assert second_payload["order"] == 1

            listing = await client.get(f"/trails/{trail_id}/activities")
            assert listing.status_code == 200
            activities = listing.json()
            assert [item["title"] for item in activities] == ["Scenic loop", "Warm up"]
            assert [item["order"] for item in activities] == [1, 2]

            # Move "Warm up" to the first position and update details
            update_resp = await client.patch(
                f"/trails/{trail_id}/activities/{first_payload['id']}",
                json={"order": 1, "points": 12, "notes": "Bring water"},
            )
            assert update_resp.status_code == 200
            updated_payload = update_resp.json()
            assert updated_payload["order"] == 1
            assert updated_payload["points"] == 12
            assert updated_payload["notes"] == "Bring water"

            reordered = await client.get(f"/trails/{trail_id}/activities")
            assert reordered.status_code == 200
            reordered_payload = reordered.json()
            assert [item["title"] for item in reordered_payload] == ["Warm up", "Scenic loop"]
            assert [item["order"] for item in reordered_payload] == [1, 2]

            # Delete the second activity and ensure order compacts
            delete_resp = await client.delete(
                f"/trails/{trail_id}/activities/{second_payload['id']}"
            )
            assert delete_resp.status_code == 204

            final_list = await client.get(f"/trails/{trail_id}/activities")
            assert final_list.status_code == 200
            final_payload = final_list.json()
            assert len(final_payload) == 1
            assert final_payload[0]["order"] == 1
            assert final_payload[0]["title"] == "Warm up"
    finally:
        app.dependency_overrides.pop(get_claims, None)


@pytest.mark.anyio
async def test_activity_access_restricted_to_org():
    org_id = uuid4()
    other_org = uuid4()
    organiser_claims = {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(org_id)]}
    app.dependency_overrides[get_claims] = override_claims(organiser_claims)
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            now = datetime.now(timezone.utc)
            trail_resp = await client.post(
                f"/trails/orgs/{org_id}",
                json={
                    "title": "Evening Stretch",
                    "starts_at": (now + timedelta(hours=2)).isoformat(),
                    "ends_at": (now + timedelta(hours=3)).isoformat(),
                    "capacity": 20,
                },
            )
            trail_resp.raise_for_status()
            trail_id = trail_resp.json()["id"]
    finally:
        app.dependency_overrides.pop(get_claims, None)

    app.dependency_overrides[get_claims] = override_claims(
        {"sub": str(uuid4()), "role": "organiser", "org_ids": [str(other_org)]}
    )
    try:
        async with AsyncClient(app=app, base_url="http://testserver") as client:
            response = await client.get(f"/trails/{trail_id}/activities")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_claims, None)
