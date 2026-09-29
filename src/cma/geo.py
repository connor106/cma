"""Geocoding and distance helpers."""

from __future__ import annotations

import json
import math
import urllib.parse
from dataclasses import dataclass

from cma.errors import CmaError
from cma.http import http_get

EARTH_RADIUS_MILES = 3958.7613
MILES_PER_LAT_DEGREE = 69.0


@dataclass(frozen=True)
class Geocode:
    input_address: str
    matched_address: str
    latitude: float
    longitude: float
    zip_code: str
    city: str
    state: str


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def bounding_square(lat: float, lng: float, radius_miles: float) -> str:
    """Redfin ``poly`` string for the square that bounds a circle of ``radius_miles``.

    Coordinates are ``longitude latitude`` pairs, closed.
    """
    d_lat = radius_miles / MILES_PER_LAT_DEGREE
    d_lng = radius_miles / (MILES_PER_LAT_DEGREE * math.cos(math.radians(lat)))
    north, south = lat + d_lat, lat - d_lat
    east, west = lng + d_lng, lng - d_lng
    corners = (
        (west, north),
        (east, north),
        (east, south),
        (west, south),
        (west, north),
    )
    return ",".join(f"{lng_c:.6f} {lat_c:.6f}" for lng_c, lat_c in corners)


def geocode_address(address: str, *, get=http_get) -> Geocode:
    """Resolve a US street address with the Census one-line geocoder."""
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + urllib.parse.urlencode(
        {
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
    )
    try:
        payload = json.loads(get(url))
    except json.JSONDecodeError as exc:
        raise CmaError("The geocoder returned an unreadable response. Try again in a few minutes.") from exc
    matches = ((payload.get("result") or {}).get("addressMatches")) or []
    if not matches:
        raise CmaError(
            "I couldn't locate that address. Include the street number, city, and state, "
            "for example `/cma428 Lawnview Ave, New Castle, Pennsylvania 16105`."
        )
    match = matches[0]
    components = match.get("addressComponents") or {}
    coords = match.get("coordinates") or {}
    zip_code = str(components.get("zip") or "")[:5]
    try:
        latitude = float(coords["y"])
        longitude = float(coords["x"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CmaError("The geocoder didn't return a map point for that address.") from exc
    if len(zip_code) != 5 or not zip_code.isdigit():
        raise CmaError("The geocoder didn't return a ZIP code for that address. Add the ZIP and try again.")
    return Geocode(
        input_address=address,
        matched_address=str(match.get("matchedAddress") or address),
        latitude=latitude,
        longitude=longitude,
        zip_code=zip_code,
        city=str(components.get("city") or ""),
        state=str(components.get("state") or ""),
    )
