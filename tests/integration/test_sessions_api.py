"""
Integration tests for the Sessions API.

TDD: These tests are written FIRST, before the implementation.
Run with: pytest tests/integration/test_sessions_api.py -v
"""

import pytest
from httpx import AsyncClient


class TestSessionCreation:
    """Tests for creating new sessions."""

    @pytest.mark.asyncio
    async def test_create_session_returns_session_code(self, client: AsyncClient):
        """Creating a session returns a unique session code."""
        response = await client.post("/api/sessions", json={"host_name": "Alice"})

        assert response.status_code == 201
        data = response.json()
        assert "code" in data
        assert len(data["code"]) == 6
        assert data["code"].isalnum()

    @pytest.mark.asyncio
    async def test_create_session_creates_host_participant(self, client: AsyncClient):
        """Creating a session also creates the host as a participant."""
        response = await client.post("/api/sessions", json={"host_name": "Alice"})

        assert response.status_code == 201
        data = response.json()
        session_code = data["code"]

        # Get participants
        participants_response = await client.get(
            f"/api/sessions/{session_code}/participants"
        )

        assert participants_response.status_code == 200
        participants = participants_response.json()
        assert len(participants) == 1
        assert participants[0]["name"] == "Alice"
        assert participants[0]["is_host"] == True

    @pytest.mark.asyncio
    async def test_create_session_requires_host_name(self, client: AsyncClient):
        """Creating a session requires a host name."""
        response = await client.post("/api/sessions", json={})

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_session_codes_are_unique(self, client: AsyncClient):
        """Each session gets a unique code."""
        codes = set()
        for _ in range(5):
            response = await client.post("/api/sessions", json={"host_name": "Host"})
            assert response.status_code == 201
            codes.add(response.json()["code"])

        assert len(codes) == 5


class TestSessionRetrieval:
    """Tests for retrieving sessions."""

    @pytest.mark.asyncio
    async def test_get_session_by_code(self, client: AsyncClient):
        """Can retrieve a session by its code."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_code = create_response.json()["code"]

        # Get session
        response = await client.get(f"/api/sessions/{session_code}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == session_code
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_404(self, client: AsyncClient):
        """Getting a non-existent session returns 404."""
        response = await client.get("/api/sessions/NOTFND")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_session_code_is_case_insensitive(self, client: AsyncClient):
        """Session codes are case-insensitive."""
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_code = create_response.json()["code"]

        # Try getting with different case
        response = await client.get(f"/api/sessions/{session_code.lower()}")
        assert response.status_code == 200

        response = await client.get(f"/api/sessions/{session_code.upper()}")
        assert response.status_code == 200


class TestSessionQRCode:
    """Tests for QR code generation."""

    @pytest.mark.asyncio
    async def test_get_session_qr_code(self, client: AsyncClient):
        """Can get a QR code image for a session."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_code = create_response.json()["code"]

        # Get QR code
        response = await client.get(f"/api/sessions/{session_code}/qr")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


class TestSessionSummary:
    """Tests for session bill summary."""

    @pytest.mark.asyncio
    async def test_get_session_summary(self, client: AsyncClient):
        """Can get the bill split summary for a session."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_code = create_response.json()["code"]

        # Get summary
        response = await client.get(f"/api/sessions/{session_code}/summary")

        assert response.status_code == 200
        data = response.json()
        assert "participants" in data
        assert "unassigned_items" in data

    @pytest.mark.asyncio
    async def test_summary_calculates_bill_split(self, client: AsyncClient):
        """Summary correctly calculates bill split."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_data = create_response.json()
        session_code = session_data["code"]
        host_token = session_data["host_token"]

        # Add another participant
        await client.post(
            f"/api/sessions/{session_code}/participants", json={"name": "Bob"}
        )

        # Add items (requires host token)
        burger_response = await client.post(
            f"/api/sessions/{session_code}/items",
            json={"name": "Burger", "price": "15.00"},
            headers={"X-Host-Token": host_token},
        )
        burger_id = burger_response.json()["id"]

        salad_response = await client.post(
            f"/api/sessions/{session_code}/items",
            json={"name": "Salad", "price": "12.00"},
            headers={"X-Host-Token": host_token},
        )
        salad_id = salad_response.json()["id"]

        # Get participants to get their IDs
        participants_response = await client.get(
            f"/api/sessions/{session_code}/participants"
        )
        participants = participants_response.json()
        alice_id = next(p["id"] for p in participants if p["name"] == "Alice")
        bob_id = next(p["id"] for p in participants if p["name"] == "Bob")

        # Assign items
        await client.post(
            f"/api/sessions/{session_code}/assignments",
            json={"item_id": burger_id, "participant_id": alice_id},
        )
        await client.post(
            f"/api/sessions/{session_code}/assignments",
            json={"item_id": salad_id, "participant_id": bob_id},
        )

        # Set tips
        await client.put(
            f"/api/sessions/{session_code}/participants/{alice_id}",
            json={"tip_percentage": "20.00"},
        )
        await client.put(
            f"/api/sessions/{session_code}/participants/{bob_id}",
            json={"tip_percentage": "15.00"},
        )

        # Get summary
        response = await client.get(f"/api/sessions/{session_code}/summary")

        assert response.status_code == 200
        data = response.json()

        # Find Alice's summary
        alice_summary = next(
            p for p in data["participants"] if p["participant_name"] == "Alice"
        )
        assert float(alice_summary["items_subtotal"]) == 15.00
        assert float(alice_summary["tip_amount"]) == 3.00  # 20% of $15

        # Find Bob's summary
        bob_summary = next(
            p for p in data["participants"] if p["participant_name"] == "Bob"
        )
        assert float(bob_summary["items_subtotal"]) == 12.00
        assert float(bob_summary["tip_amount"]) == 1.80  # 15% of $12


class TestSessionDeletion:
    """Tests for deleting sessions."""

    @pytest.mark.asyncio
    async def test_delete_session(self, client: AsyncClient):
        """Can delete a session."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_data = create_response.json()
        session_code = session_data["code"]
        host_token = session_data["host_token"]

        # Delete session (requires host token)
        response = await client.delete(
            f"/api/sessions/{session_code}", headers={"X-Host-Token": host_token}
        )

        assert response.status_code == 204

        # Verify session is gone
        get_response = await client.get(f"/api/sessions/{session_code}")
        assert get_response.status_code == 404


class TestReceiptUpload:
    """Tests for uploading receipt images."""

    @pytest.mark.asyncio
    async def test_upload_receipt_invalid_session(self, client: AsyncClient):
        """Upload to non-existent session returns 404."""
        # Create a minimal fake image (1x1 white JPEG)
        from io import BytesIO

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="white")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        response = await client.post(
            "/api/sessions/INVALID/receipt",
            files={"file": ("receipt.jpg", img_bytes, "image/jpeg")},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_receipt_invalid_file_type(self, client: AsyncClient):
        """Upload of non-image file returns 400."""
        # Create session
        create_response = await client.post(
            "/api/sessions", json={"host_name": "Alice"}
        )
        session_data = create_response.json()
        session_code = session_data["code"]
        host_token = session_data["host_token"]

        # Try to upload a text file (requires host token)
        response = await client.post(
            f"/api/sessions/{session_code}/receipt",
            files={"file": ("receipt.txt", b"not an image", "text/plain")},
            headers={"X-Host-Token": host_token},
        )

        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"]


class TestNearbyDiscovery:
    """Tests for nearby session discovery."""

    @pytest.mark.asyncio
    async def test_nearby_sessions_empty_by_default(self, client: AsyncClient):
        """Nearby sessions returns empty list when no sessions exist."""
        response = await client.get("/api/sessions/nearby")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert data["sessions"] == []

    @pytest.mark.asyncio
    async def test_create_session_with_location(self, client: AsyncClient):
        """Creating a session with location stores the geohash."""
        response = await client.post(
            "/api/sessions",
            json={"host_name": "Alice", "latitude": 40.7128, "longitude": -74.0060},
        )

        assert response.status_code == 201
        data = response.json()
        assert "code" in data

    @pytest.mark.asyncio
    async def test_nearby_with_location_finds_sessions(self, client: AsyncClient):
        """Nearby endpoint with lat/lng finds sessions created at same location."""
        # Create session with location
        create_response = await client.post(
            "/api/sessions",
            json={"host_name": "Alice", "latitude": 40.7128, "longitude": -74.0060},
        )
        assert create_response.status_code == 201
        session_code = create_response.json()["code"]

        # Search nearby with same coordinates
        nearby_response = await client.get(
            "/api/sessions/nearby", params={"lat": 40.7128, "lng": -74.0060}
        )
        assert nearby_response.status_code == 200
        data = nearby_response.json()

        assert len(data["sessions"]) >= 1
        assert any(s["code"] == session_code for s in data["sessions"])

    @pytest.mark.asyncio
    async def test_nearby_location_different_area_no_match(self, client: AsyncClient):
        """Sessions in different areas don't match by location."""
        # Create session in NYC with a different IP (to avoid network_hash match)
        create_response = await client.post(
            "/api/sessions",
            json={"host_name": "Alice", "latitude": 40.7128, "longitude": -74.0060},
            headers={"X-Forwarded-For": "10.0.0.1"},  # NYC user's IP
        )
        assert create_response.status_code == 201

        # Search nearby in San Francisco (different location AND different IP)
        nearby_response = await client.get(
            "/api/sessions/nearby",
            params={"lat": 37.7749, "lng": -122.4194},
            headers={"X-Forwarded-For": "192.168.1.1"},  # SF user's IP
        )
        assert nearby_response.status_code == 200
        data = nearby_response.json()

        # Should not find NYC session from SF (different network AND far away)
        assert len(data["sessions"]) == 0

    @pytest.mark.asyncio
    async def test_nearby_with_invalid_coordinates(self, client: AsyncClient):
        """Invalid coordinates are handled gracefully."""
        # Invalid latitude (>90)
        response = await client.get(
            "/api/sessions/nearby", params={"lat": 91, "lng": 0}
        )
        assert response.status_code == 422  # Validation error
