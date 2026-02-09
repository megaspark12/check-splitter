"""Geolocation utilities for nearby session discovery."""

# Geohash character set (base32)
_GEOHASH_CHARS = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode_geohash(latitude: float, longitude: float, precision: int = 7) -> str:
    """
    Encode latitude/longitude into a geohash string.
    
    Precision levels (approximate):
    - 5: ~4.9km × 4.9km
    - 6: ~1.2km × 0.6km
    - 7: ~150m × 150m  (good for restaurants)
    - 8: ~40m × 20m
    
    Args:
        latitude: Latitude (-90 to 90)
        longitude: Longitude (-180 to 180)
        precision: Length of geohash (default 7 = ~150m accuracy)
    
    Returns:
        Geohash string
    """
    if not (-90 <= latitude <= 90):
        raise ValueError(f"Latitude must be between -90 and 90, got {latitude}")
    if not (-180 <= longitude <= 180):
        raise ValueError(f"Longitude must be between -180 and 180, got {longitude}")
    
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    
    geohash = []
    bits = 0
    bit_count = 0
    is_longitude = True  # Start with longitude
    
    while len(geohash) < precision:
        if is_longitude:
            mid = (lon_range[0] + lon_range[1]) / 2
            if longitude >= mid:
                bits = (bits << 1) | 1
                lon_range[0] = mid
            else:
                bits = bits << 1
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if latitude >= mid:
                bits = (bits << 1) | 1
                lat_range[0] = mid
            else:
                bits = bits << 1
                lat_range[1] = mid
        
        is_longitude = not is_longitude
        bit_count += 1
        
        if bit_count == 5:
            geohash.append(_GEOHASH_CHARS[bits])
            bits = 0
            bit_count = 0
    
    return "".join(geohash)


def get_geohash_neighbors(geohash: str) -> list[str]:
    """
    Get all 8 neighboring geohash cells plus the center cell.
    
    This helps catch edge cases where users are at the boundary between cells.
    
    Returns:
        List of 9 geohash strings (center + 8 neighbors)
    """
    # Direction encoding for neighbor calculation
    _NEIGHBORS = {
        'n': ('p0r21436x8zb9dcf5h7kjnmqesgutwvy', 'bc01fg45238967deuvhjyznpkmstqrwx'),
        's': ('14365h7k9dcfesgujnmqp0r2twvyx8zb', '238967debc01teleuvhjyznpkmstqrwx'),
        'e': ('bc01fg45238967deuvhjyznpkmstqrwx', 'p0r21436x8zb9dcf5h7kjnmqesgutwvy'),
        'w': ('238967debc01fg45kmstqrwxuvhjyznp', '14365h7k9dcfesgujnmqp0r2twvyx8zb'),
    }
    _BORDERS = {
        'n': ('prxz', 'bcfguvyz'),
        's': ('028b', '0145hjnp'),
        'e': ('bcfguvyz', 'prxz'),
        'w': ('0145hjnp', '028b'),
    }
    
    def get_neighbor(gh: str, direction: str) -> str:
        """Calculate adjacent geohash in given direction."""
        if not gh:
            return gh
        
        last_char = gh[-1]
        parent = gh[:-1]
        char_type = len(gh) % 2  # 0 = even (longitude), 1 = odd (latitude)
        
        # Check if we need to recurse to parent
        if last_char in _BORDERS[direction][char_type] and parent:
            parent = get_neighbor(parent, direction)
        
        # Find position in neighbor lookup and get new character
        pos = _NEIGHBORS[direction][char_type].index(last_char)
        return parent + _GEOHASH_CHARS[pos]
    
    # Get all neighbors
    neighbors = [geohash]  # Include center
    
    try:
        n = get_neighbor(geohash, 'n')
        s = get_neighbor(geohash, 's')
        e = get_neighbor(geohash, 'e')
        w = get_neighbor(geohash, 'w')
        
        neighbors.extend([n, s, e, w])
        neighbors.append(get_neighbor(n, 'e'))  # NE
        neighbors.append(get_neighbor(n, 'w'))  # NW
        neighbors.append(get_neighbor(s, 'e'))  # SE
        neighbors.append(get_neighbor(s, 'w'))  # SW
    except (ValueError, IndexError):
        # If neighbor calculation fails, just return center
        pass
    
    return neighbors


def create_location_hash(latitude: float, longitude: float) -> str:
    """
    Create a location hash for nearby session matching.
    
    Uses precision 7 (~150m) which is ideal for restaurant-scale proximity.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
    
    Returns:
        Geohash string suitable for matching nearby sessions
    """
    return encode_geohash(latitude, longitude, precision=7)
