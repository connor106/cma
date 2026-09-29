"""Run a comparative market analysis for one address."""

from __future__ import annotations

from datetime import datetime

from cma.geo import geocode_address
from cma.http import http_get
from cma.listings import (
    EASTERN,
    fetch_listings,
    fetch_region,
    homes_to_comps,
    prefer_residential,
)
from cma.models import Report, Subject
from cma.parse import parse_command
from cma.select import indicate_value, select_comps
from cma.subject import apply_listing_facts, lookup_assessment

RADIUS_MILES = 1.0
SOLD_WITHIN_DAYS = 365


def analyze(text: str, *, get=http_get) -> Report:
    """Build a CMA from a Slack message such as ``/cma428 Lawnview Ave, ...``."""
    address = parse_command(text)
    located = geocode_address(address, get=get)
    subject = Subject(
        address=address,
        matched_address=located.matched_address,
        latitude=located.latitude,
        longitude=located.longitude,
        zip_code=located.zip_code,
        city=located.city,
        state=located.state,
    )
    region_id, market = fetch_region(located.zip_code, get=get)
    raw_active, raw_sold = fetch_listings(
        latitude=located.latitude,
        longitude=located.longitude,
        region_id=region_id,
        market=market,
        radius_miles=RADIUS_MILES,
        sold_within_days=SOLD_WITHIN_DAYS,
        get=get,
    )
    today = datetime.now(EASTERN).date()
    active = homes_to_comps(
        raw_active,
        group="active",
        origin_lat=located.latitude,
        origin_lng=located.longitude,
        radius_miles=RADIUS_MILES,
        sold_within_days=SOLD_WITHIN_DAYS,
        today=today,
    )
    sold = homes_to_comps(
        raw_sold,
        group="sold",
        origin_lat=located.latitude,
        origin_lng=located.longitude,
        radius_miles=RADIUS_MILES,
        sold_within_days=SOLD_WITHIN_DAYS,
        today=today,
    )
    active = prefer_residential(active, raw_active)
    sold = prefer_residential(sold, raw_sold)
    combined = apply_listing_facts(subject, sold + active)
    sold = [comp for comp in combined if comp.group == "sold"]
    active = [comp for comp in combined if comp.group == "active"]
    lookup_assessment(subject, get=get)
    chosen = select_comps(sold, active, subject, today=today)
    return Report(
        subject=subject,
        comps=chosen,
        pool_sold=len(sold),
        pool_active=len(active),
        radius_miles=RADIUS_MILES,
        sold_within_days=SOLD_WITHIN_DAYS,
        indication=indicate_value(subject, chosen),
    )
