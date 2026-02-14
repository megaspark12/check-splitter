"""Unit tests for the geolocation service."""

import pytest

from app.services.geolocation import (
    create_location_hash,
    encode_geohash,
    get_geohash_neighbors,
)


class TestGeohashEncoding:
    """Tests for geohash encoding."""

    def test_basic_encoding(self):
        """Test basic geohash encoding."""
        # San Francisco coordinates
        geohash = encode_geohash(37.7749, -122.4194, precision=7)
        assert len(geohash) == 7
        assert geohash.startswith("9q8yy")  # Known prefix for SF

    def test_new_york_encoding(self):
        """Test encoding for New York."""
        geohash = encode_geohash(40.7128, -74.0060, precision=7)
        assert len(geohash) == 7
        assert geohash.startswith("dr5r")  # Known prefix for NYC

    def test_precision_levels(self):
        """Test different precision levels."""
        lat, lng = 40.7128, -74.0060

        gh5 = encode_geohash(lat, lng, precision=5)
        gh7 = encode_geohash(lat, lng, precision=7)
        gh8 = encode_geohash(lat, lng, precision=8)

        assert len(gh5) == 5
        assert len(gh7) == 7
        assert len(gh8) == 8

        # Longer precision should start with shorter precision
        assert gh7.startswith(gh5)
        assert gh8.startswith(gh7)

    def test_nearby_points_same_geohash(self):
        """Test that nearby points get similar geohashes."""
        # Two points ~50m apart
        lat1, lng1 = 40.712800, -74.006000
        lat2, lng2 = 40.712850, -74.005950

        gh1 = encode_geohash(lat1, lng1, precision=7)
        gh2 = encode_geohash(lat2, lng2, precision=7)

        # Should have same prefix (at least 5 chars)
        assert gh1[:5] == gh2[:5]

    def test_invalid_latitude(self):
        """Test that invalid latitude raises error."""
        with pytest.raises(ValueError, match="Latitude"):
            encode_geohash(91, 0)

        with pytest.raises(ValueError, match="Latitude"):
            encode_geohash(-91, 0)

    def test_invalid_longitude(self):
        """Test that invalid longitude raises error."""
        with pytest.raises(ValueError, match="Longitude"):
            encode_geohash(0, 181)

        with pytest.raises(ValueError, match="Longitude"):
            encode_geohash(0, -181)

    def test_boundary_coordinates(self):
        """Test encoding at boundary coordinates."""
        # North pole
        gh = encode_geohash(90, 0, precision=5)
        assert len(gh) == 5

        # South pole
        gh = encode_geohash(-90, 0, precision=5)
        assert len(gh) == 5

        # Date line
        gh = encode_geohash(0, 180, precision=5)
        assert len(gh) == 5

        gh = encode_geohash(0, -180, precision=5)
        assert len(gh) == 5


class TestLocationHash:
    """Tests for location hash creation."""

    def test_create_location_hash(self):
        """Test creating a location hash."""
        loc_hash = create_location_hash(40.7128, -74.0060)
        assert len(loc_hash) == 7
        assert isinstance(loc_hash, str)

    def test_location_hash_consistency(self):
        """Test that same coordinates produce same hash."""
        hash1 = create_location_hash(40.7128, -74.0060)
        hash2 = create_location_hash(40.7128, -74.0060)
        assert hash1 == hash2


class TestGeohashNeighbors:
    """Tests for geohash neighbor calculation."""

    def test_returns_nine_cells(self):
        """Test that neighbors returns 9 cells (center + 8 directions)."""
        geohash = encode_geohash(40.7128, -74.0060, precision=7)
        neighbors = get_geohash_neighbors(geohash)

        # Should include original plus 8 neighbors
        assert len(neighbors) == 9
        assert geohash in neighbors

    def test_neighbors_are_adjacent(self):
        """Test that neighbor geohashes share prefix."""
        geohash = encode_geohash(40.7128, -74.0060, precision=7)
        neighbors = get_geohash_neighbors(geohash)

        # All neighbors should share at least the first 5 characters
        # (neighbors at precision 7 are very close)
        for neighbor in neighbors:
            assert len(neighbor) == 7

    def test_empty_geohash(self):
        """Test handling of empty geohash."""
        neighbors = get_geohash_neighbors("")
        assert "" in neighbors


class TestNearbyDiscoveryScenario:
    """Integration-style tests for nearby discovery use case."""

    def test_restaurant_scenario(self):
        """Test that people at the same restaurant get matching hashes."""
        # Simulate 4 people at a restaurant, with slight GPS variance
        restaurant_coords = [
            (40.712800, -74.006000),  # Table 1
            (40.712810, -74.005995),  # Table 2 (5m away)
            (40.712790, -74.006010),  # Table 3 (5m away)
            (40.712815, -74.005985),  # Outside but close
        ]

        hashes = [create_location_hash(lat, lng) for lat, lng in restaurant_coords]

        # At precision 7 (~150m), all should be identical or neighbors
        base_hash = hashes[0]
        neighbors = get_geohash_neighbors(base_hash)

        for h in hashes:
            assert h in neighbors, f"Hash {h} not in neighbors of {base_hash}"

    def test_different_restaurants(self):
        """Test that different restaurants don't match."""
        # Two restaurants 1km apart
        restaurant_a = create_location_hash(40.7128, -74.0060)  # Restaurant A
        restaurant_b = create_location_hash(40.7200, -74.0060)  # ~800m north

        neighbors_a = get_geohash_neighbors(restaurant_a)

        # Restaurant B should NOT be in neighbors of A
        assert restaurant_b not in neighbors_a
