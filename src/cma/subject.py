"""Subject property facts.

Listings win when the address is on the market or recently sold. Otherwise,
Lawrence County's public assessment layer supplies beds, baths, and square
footage for 161xx ZIP codes. Assessed value is never treated as market value.
"""

from __future__ import annotations

import json
import urllib.parse

from cma.http import http_get
from cma.listings import same_property, street_key
from cma.models import Comp, Subject

LAWRENCE_PARCELS = (
    "https://gis.leoc.net:6443/arcgis/rest/services/LAWRENCEGIS/TaxParcelCAMA/MapServer/1/query"
)


def apply_listing_facts(subject: Subject, comps: list[Comp]) -> list[Comp]:
    """Copy facts from a listing of the subject and remove it from the comp pool."""
    kept: list[Comp] = []
    match: Comp | None = None
    for comp in comps:
        if same_property(subject.address, comp.address) or same_property(subject.matched_address, comp.address):
            match = comp
            continue
        kept.append(comp)
    if match is not None:
        subject.beds = match.beds if match.beds is not None else subject.beds
        subject.baths = match.baths if match.baths is not None else subject.baths
        subject.sqft = match.sqft if match.sqft is not None else subject.sqft
        subject.year_built = match.year_built if match.year_built is not None else subject.year_built
        subject.facts_source = "the current or recent listing"
    return kept


def lookup_assessment(subject: Subject, *, get=http_get) -> None:
    """Fill missing subject facts from the Lawrence County assessment map."""
    if subject.state not in {"PA", "PENNSYLVANIA"} or not subject.zip_code.startswith("161"):
        return
    if subject.beds is not None and subject.sqft is not None:
        return
    key = street_key(subject.address) or street_key(subject.matched_address)
    if key is None:
        return
    number, name = key
    prefix = _situs_prefix(subject.address) or _situs_prefix(subject.matched_address)
    if prefix is None:
        return
    safe_prefix = prefix.replace("'", "''").replace("%", "").replace("_", "").upper()
    where = f"UPPER(SITUS) LIKE '{safe_prefix}%'"
    url = LAWRENCE_PARCELS + "?" + urllib.parse.urlencode(
        {
            "f": "json",
            "where": where,
            "outFields": "SITUS,BEDROOMS,F_BATHS,H_BATHS,SQFT,YR_BUILT,CITY,ZIP",
            "returnGeometry": "false",
        }
    )
    try:
        payload = json.loads(get(url, timeout=20))
    except Exception:
        return
    features = payload.get("features") or []
    attributes = _best_parcel(features, number=number, name=name, zip_code=subject.zip_code)
    if attributes is None:
        return
    beds = _optional_float(attributes.get("BEDROOMS"))
    full = _optional_float(attributes.get("F_BATHS")) or 0.0
    half = _optional_float(attributes.get("H_BATHS")) or 0.0
    baths = full + 0.5 * half if (attributes.get("F_BATHS") is not None or attributes.get("H_BATHS") is not None) else None
    sqft = _optional_int(attributes.get("SQFT"))
    year_built = _optional_int(attributes.get("YR_BUILT"))
    if subject.beds is None and beds and beds > 0:
        subject.beds = beds
    if subject.baths is None and baths and baths > 0:
        subject.baths = baths
    if subject.sqft is None and sqft and sqft > 0:
        subject.sqft = sqft
    if subject.year_built is None and year_built and year_built > 1800:
        subject.year_built = year_built
    if any(value is not None for value in (subject.beds, subject.baths, subject.sqft)):
        subject.facts_source = subject.facts_source or "the Lawrence County assessment record"


def _best_parcel(features: list[dict], *, number: str, name: str, zip_code: str) -> dict | None:
    ranked: list[tuple[int, dict]] = []
    for feature in features:
        attributes = feature.get("attributes") or {}
        situs = str(attributes.get("SITUS") or "")
        key = street_key(situs)
        if key != (number, name):
            continue
        score = 0
        if str(attributes.get("ZIP") or "").startswith(zip_code):
            score += 2
        if _optional_int(attributes.get("SQFT")):
            score += 2
        if _optional_float(attributes.get("BEDROOMS")):
            score += 1
        ranked.append((score, attributes))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(round(number))


def _situs_prefix(address: str) -> str | None:
    """Street number plus name, keeping a leading direction (``123 N Main``)."""
    line = address.split(",")[0].strip()
    parts = line.split()
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    suffixes = {
        "ave", "avenue", "st", "street", "rd", "road", "dr", "drive", "ln", "lane",
        "ct", "court", "blvd", "boulevard", "way", "pl", "place", "cir", "circle",
        "ter", "terrace", "trl", "trail", "hwy", "highway", "pkwy", "parkway",
    }
    tokens = parts[1:]
    while tokens and tokens[-1].lower().rstrip(".") in suffixes:
        tokens.pop()
    if not tokens:
        return None
    return " ".join([parts[0], *tokens])
