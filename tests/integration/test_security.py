"""
Integration tests for security features.

Tests host token authentication and session expiry enforcement.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


class TestHostTokenAuthentication:
    """Tests for host token authentication on protected endpoints."""

    @pytest.mark.asyncio
    async def test_create_session_returns_host_token(self, client: AsyncClient):
        """Creating a session returns a host token."""
        response = await client.post("/api/sessions", json={"host_name": "Alice"})

        assert response.status_code == 201
        data = response.json()
        assert "host_token" in data
        assert data["host_token"] is not None
        assert len(data["host_token"]) > 20  # Token should be reasonably long

    @pytest.mark.asyncio
    async def test_get_session_does_not_return_host_token(self, client: AsyncClient):
        """Fetching a session does NOT return the host token (only on creation)."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        code = create_response.json()["code"]

        # Fetch session
        get_response = await client.get(f"/api/sessions/{code}")
        data = get_response.json()

        assert data.get("host_token") is None

    @pytest.mark.asyncio
    async def test_add_item_requires_host_token(self, client: AsyncClient):
        """Adding an item without host token returns 401."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        code = create_response.json()["code"]

        # Try to add item without token
        response = await client.post(
            f"/api/sessions/{code}/items",
            json={"name": "Burger", "price": 10.99, "quantity": 1},
        )

        assert response.status_code == 401
        assert "Host token required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_add_item_with_valid_host_token_succeeds(self, client: AsyncClient):
        """Adding an item with valid host token succeeds."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Add item with token
        response = await client.post(
            f"/api/sessions/{code}/items",
            json={"name": "Burger", "price": 10.99, "quantity": 1},
            headers={"X-Host-Token": host_token},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Burger"

    @pytest.mark.asyncio
    async def test_add_item_with_invalid_host_token_fails(self, client: AsyncClient):
        """Adding an item with invalid host token returns 403."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        code = create_response.json()["code"]

        # Try with wrong token
        response = await client.post(
            f"/api/sessions/{code}/items",
            json={"name": "Burger", "price": 10.99, "quantity": 1},
            headers={"X-Host-Token": "wrong-token"},
        )

        assert response.status_code == 403
        assert "Invalid host token" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_item_requires_host_token(self, client: AsyncClient):
        """Deleting an item requires host token."""
        # Create session and add item
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Add item with token
        item_response = await client.post(
            f"/api/sessions/{code}/items",
            json={"name": "Burger", "price": 10.99, "quantity": 1},
            headers={"X-Host-Token": host_token},
        )
        item_id = item_response.json()["id"]

        # Try to delete without token
        response = await client.delete(f"/api/sessions/{code}/items/{item_id}")
        assert response.status_code == 401

        # Delete with token
        response = await client.delete(
            f"/api/sessions/{code}/items/{item_id}",
            headers={"X-Host-Token": host_token},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_session_requires_host_token(self, client: AsyncClient):
        """Deleting a session requires host token."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Try to delete without token
        response = await client.delete(f"/api/sessions/{code}")
        assert response.status_code == 401

        # Delete with token
        response = await client.delete(
            f"/api/sessions/{code}", headers={"X-Host-Token": host_token}
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_participant_requires_host_token(self, client: AsyncClient):
        """Removing a participant requires host token."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Add a participant (no auth required)
        join_response = await client.post(
            f"/api/sessions/{code}/participants", json={"name": "Bob"}
        )
        participant_id = join_response.json()["id"]

        # Try to remove without token
        response = await client.delete(
            f"/api/sessions/{code}/participants/{participant_id}"
        )
        assert response.status_code == 401

        # Remove with token
        response = await client.delete(
            f"/api/sessions/{code}/participants/{participant_id}",
            headers={"X-Host-Token": host_token},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_create_discount_requires_host_token(self, client: AsyncClient):
        """Creating a discount requires host token."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Try without token
        response = await client.post(
            f"/api/sessions/{code}/discounts",
            json={"name": "10% off", "discount_type": "percentage", "value": 10},
        )
        assert response.status_code == 401

        # With token
        response = await client.post(
            f"/api/sessions/{code}/discounts",
            json={"name": "10% off", "discount_type": "percentage", "value": 10},
            headers={"X-Host-Token": host_token},
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_read_operations_do_not_require_host_token(self, client: AsyncClient):
        """Read-only operations (GET) do not require host token."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Add an item for testing
        await client.post(
            f"/api/sessions/{code}/items",
            json={"name": "Burger", "price": 10.99, "quantity": 1},
            headers={"X-Host-Token": host_token},
        )

        # GET endpoints should work without token
        assert (await client.get(f"/api/sessions/{code}")).status_code == 200
        assert (await client.get(f"/api/sessions/{code}/items")).status_code == 200
        assert (
            await client.get(f"/api/sessions/{code}/participants")
        ).status_code == 200
        assert (await client.get(f"/api/sessions/{code}/discounts")).status_code == 200

    @pytest.mark.asyncio
    async def test_join_session_does_not_require_host_token(self, client: AsyncClient):
        """Joining a session does not require host token."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        code = create_response.json()["code"]

        # Join without token
        response = await client.post(
            f"/api/sessions/{code}/participants", json={"name": "Bob"}
        )
        assert response.status_code == 201


class TestSessionExpiry:
    """Tests for session expiry enforcement."""

    @pytest.mark.asyncio
    async def test_expired_session_returns_410(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Accessing an expired session returns 410 Gone."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]

        # Manually set session as expired in the database
        result = await db_session.execute(select(Session).where(Session.code == code))
        session = result.scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.commit()

        # Try to access the session
        response = await client.get(f"/api/sessions/{code}")
        assert response.status_code == 410
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_expired_session_blocks_all_operations(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """An expired session blocks all read and write operations."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Expire the session
        result = await db_session.execute(select(Session).where(Session.code == code))
        session = result.scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.commit()

        # All operations should return 410
        assert (await client.get(f"/api/sessions/{code}")).status_code == 410
        assert (await client.get(f"/api/sessions/{code}/items")).status_code == 410
        assert (
            await client.get(f"/api/sessions/{code}/participants")
        ).status_code == 410
        assert (
            await client.post(
                f"/api/sessions/{code}/participants", json={"name": "Bob"}
            )
        ).status_code == 410
        assert (
            await client.post(
                f"/api/sessions/{code}/items",
                json={"name": "Burger", "price": 10.99, "quantity": 1},
                headers={"X-Host-Token": host_token},
            )
        ).status_code == 410

    @pytest.mark.asyncio
    async def test_active_session_works_normally(self, client: AsyncClient):
        """A non-expired session works normally."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        data = create_response.json()
        code = data["code"]
        host_token = data["host_token"]

        # Session should work
        response = await client.get(f"/api/sessions/{code}")
        assert response.status_code == 200

        # Add item should work
        response = await client.post(
            f"/api/sessions/{code}/items",
            json={"name": "Burger", "price": 10.99, "quantity": 1},
            headers={"X-Host-Token": host_token},
        )
        assert response.status_code == 201
