"""Fetch active and recently sold homes from Redfin's public map search."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

from cma.errors import CmaError
from cma.geo import bounding_square, haversine_miles
from cma.http import http_get
from cma.models import Comp

EASTERN = ZoneInfo("America/New_York")
GIS_URL = "https://www.redfin.com/stingray/api/gis"
# House, condo, and townhouse. Land, multi-family, and other types are dropped
# unless the residential pool is too thin to build a comp set.
RESIDENTIAL_UIPT = {1, 2, 3}
MIN_PRICE = 5_000

_STREET_SUFFIXES = {
    "ave", "avenue", "st", "street", "rd", "road", "dr", "drive", "ln", "lane",
    "ct", "court", "blvd", "boulevard", "way", "pl", "place", "cir", "circle",
    "ter", "terrace", "trl", "trail", "hwy", "highway", "pkwy", "parkway",
}
_DIRECTIONS = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "north", "south", "east", "west"}


def parse_region(html: str, zip_code: str) -> tuple[str, str]:
    """Pull the Redfin ZIP region id and market name out of a ZIP search page."""
    normalized = html.replace('\\"', '"').replace("\\u0026", "&").replace("\\u002F", "/")
    named = re.search(
        rf'"region_id":(\d+),"region_type":2,"region_name":"{re.escape(zip_code)}"',
        normalized,
    )
    if named:
        region_id = named.group(1)
    else:
        ids = [region for region in re.findall(r"region_id=(\d+)&region_type=2", normalized) if region != zip_code]
        if not ids:
            raise CmaError(f"I couldn't find a listing search for ZIP {zip_code}.")
        region_id = Counter(ids).most_common(1)[0][0]
    markets = re.findall(r"market=([a-z0-9\-]+)", normalized)
    market = Counter(markets).most_common(1)[0][0] if markets else ""
    return region_id, market


def fetch_region(zip_code: str, *, get=http_get) -> tuple[str, str]:
    html = get(f"https://www.redfin.com/zipcode/{zip_code}")
    if "Page Not Found" in html[:500] or "region_id" not in html:
        raise CmaError(f"I couldn't find a listing search for ZIP {zip_code}.")
    return parse_region(html, zip_code)


def fetch_listings(
    *,
    latitude: float,
    longitude: float,
    region_id: str,
    market: str,
    radius_miles: float,
    sold_within_days: int,
    get=http_get,
) -> tuple[list[dict], list[dict]]:
    """Return raw active and sold home records inside the search square."""
    poly = bounding_square(latitude, longitude, radius_miles)
    active = _gis(
        region_id=region_id,
        market=market,
        poly=poly,
        extra={"mpt": "1", "status": "1"},
        get=get,
    )
    sold = _gis(
        region_id=region_id,
        market=market,
        poly=poly,
        extra={"mpt": "99", "status": "9", "sold_within_days": str(sold_within_days)},
        get=get,
    )
    return active, sold


def homes_to_comps(
    homes: list[dict],
    *,
    group: str,
    origin_lat: float,
    origin_lng: float,
    radius_miles: float,
    sold_within_days: int,
    today: date | None = None,
) -> list[Comp]:
    """Keep residential homes within ``radius_miles`` and map them to comps."""
    today = today or datetime.now(EASTERN).date()
    comps: list[Comp] = []
    seen: set[str] = set()
    for home in homes:
        comp = _map_home(home, group=group, origin_lat=origin_lat, origin_lng=origin_lng, today=today)
        if comp is None or comp.distance_miles > radius_miles:
            continue
        if group == "sold" and comp.sold_date is not None:
            age = (today - comp.sold_date).days
            if age > sold_within_days or age < -1:
                continue
        key = comp.property_id or comp.url or comp.address
        if key in seen:
            continue
        seen.add(key)
        comps.append(comp)
    return comps


def prefer_residential(comps: list[Comp], homes: list[dict]) -> list[Comp]:
    """Drop non-residential types when the remaining set still has homes.

    ``homes_to_comps`` already removed land and empty records. This pass
    prefers house, condo, and townhouse ui types when at least four remain.
    """
    by_id = {}
    for home in homes:
        property_id = home.get("propertyId")
        if property_id is not None:
            by_id[str(property_id)] = home
    residential: list[Comp] = []
    for comp in comps:
        home = by_id.get(comp.property_id or "")
        uipt = home.get("uiPropertyType") if home else None
        if uipt in RESIDENTIAL_UIPT or uipt is None:
            residential.append(comp)
    if len(residential) >= 4:
        return residential
    return comps


def street_key(address: str) -> tuple[str, str] | None:
    """Return ``(street_number, street_name)`` for matching the subject to a listing."""
    line = address.split(",")[0]
    match = re.match(r"\s*(\d+)\s+(.+)", line)
    if match is None:
        return None
    number, rest = match.group(1), match.group(2)
    tokens = re.findall(r"[A-Za-z0-9']+", rest)
    if tokens and tokens[0].lower() in _DIRECTIONS:
        tokens = tokens[1:]
    while tokens and tokens[-1].lower() in _STREET_SUFFIXES:
        tokens.pop()
    if not tokens:
        return None
    name = " ".join(tokens).lower()
    return number, name


def same_property(left: str, right: str) -> bool:
    a = street_key(left)
    b = street_key(right)
    return a is not None and a == b


def _gis(*, region_id: str, market: str, poly: str, extra: dict[str, str], get) -> list[dict]:
    homes: list[dict] = []
    for page in range(1, 4):
        params = {
            "al": "1",
            "include_nearby_homes": "true",
            "num_homes": "350",
            "page_number": str(page),
            "region_id": region_id,
            "region_type": "2",
            "start": str((page - 1) * 350),
            "uipt": "1,2,3,4,5,6,7,8",
            "v": "8",
            "poly": poly,
            **extra,
        }
        if market:
            params["market"] = market
        url = GIS_URL + "?" + urllib.parse.urlencode(params)
        batch = _parse_gis(get(url))
        homes.extend(batch)
        if len(batch) < 350:
            break
    return homes


def _parse_gis(body: str) -> list[dict]:
    if body.startswith("{}&&"):
        body = body[4:]
    if body.lstrip().startswith("<"):
        raise CmaError("The listing service blocked the request. Try again in a few minutes.")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CmaError("The listing service returned an unreadable response. Try again in a few minutes.") from exc
    message = data.get("errorMessage")
    if message not in (None, "Success"):
        raise CmaError("The listing search failed. Try again in a few minutes.")
    return ((data.get("payload") or {}).get("homes")) or []


def _map_home(home: dict, *, group: str, origin_lat: float, origin_lng: float, today: date) -> Comp | None:
    if home.get("hideSalePrice"):
        return None
    mls_status = str(home.get("mlsStatus") or "")
    normalized = _group_for_status(mls_status)
    if normalized != group:
        return None
    price = _int_value(home.get("price"))
    if price is None or price < MIN_PRICE:
        return None
    lat_lng = _dict_value(home.get("latLong"))
    if not lat_lng:
        return None
    try:
        latitude = float(lat_lng["latitude"])
        longitude = float(lat_lng["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    street = _scalar(home.get("streetLine"))
    city = str(home.get("city") or "").strip()
    state = str(home.get("state") or "").strip()
    zip_code = str(home.get("zip") or home.get("postalCode") or "").strip()
    if not street:
        return None
    parts = [street]
    locality = ", ".join(part for part in (city, state) if part)
    if zip_code:
        locality = f"{locality} {zip_code}".strip()
    if locality:
        parts.append(locality)
    address = ", ".join(parts)
    uipt = home.get("uiPropertyType")
    beds = _float_value(home.get("beds"))
    sqft = _int_value(home.get("sqFt"))
    if uipt == 5:
        return None
    if (beds is None or beds <= 0) and sqft is None:
        return None
    number, name = street_key(address) or (None, None)
    path = str(home.get("url") or "")
    url = f"https://www.redfin.com{path}" if path.startswith("/") else path
    sold_date = None
    if normalized == "sold":
        sold_date = _epoch_date(home.get("soldDate"))
    return Comp(
        address=address,
        group=normalized,
        mls_status=mls_status,
        price=price,
        beds=beds,
        baths=_float_value(home.get("baths")),
        sqft=sqft,
        year_built=_int_value(home.get("yearBuilt")),
        distance_miles=haversine_miles(origin_lat, origin_lng, latitude, longitude),
        sold_date=sold_date,
        dom=_int_value(home.get("dom")) if normalized == "active" else None,
        url=url,
        property_id=str(home["propertyId"]) if home.get("propertyId") is not None else None,
        street_number=number,
        street_name=name,
    )


def _group_for_status(mls_status: str) -> str | None:
    label = mls_status.strip().lower()
    if label in {"closed", "sold"}:
        return "sold"
    if label in {"active", "pending", "contingent", "coming soon", "active under contract"}:
        return "active"
    return None


def _dict_value(node) -> dict | None:
    if isinstance(node, dict) and isinstance(node.get("value"), dict):
        return node["value"]
    if isinstance(node, dict) and "latitude" in node:
        return node
    return None


def _scalar(node):
    if isinstance(node, dict) and "value" in node:
        return node.get("value")
    return node


def _int_value(node) -> int | None:
    value = _scalar(node)
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _float_value(node) -> float | None:
    value = _scalar(node)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _epoch_date(value) -> date | None:
    value = _scalar(value)
    if value is None:
        return None
    try:
        millis = float(value)
    except (TypeError, ValueError):
        return None
    if millis > 10_000_000_000:
        millis = millis / 1000.0
    try:
        return datetime.fromtimestamp(millis, EASTERN).date()
    except (OverflowError, OSError, ValueError):
        return None
