"""Shared records for a comparative market analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Subject:
    address: str
    matched_address: str
    latitude: float
    longitude: float
    zip_code: str
    city: str
    state: str
    beds: float | None = None
    baths: float | None = None
    sqft: int | None = None
    year_built: int | None = None
    facts_source: str | None = None


@dataclass
class Comp:
    address: str
    group: str  # "sold" or "active"
    mls_status: str
    price: int
    beds: float | None
    baths: float | None
    sqft: int | None
    year_built: int | None
    distance_miles: float
    sold_date: date | None
    dom: int | None
    url: str
    property_id: str | None
    street_number: str | None
    street_name: str | None


@dataclass
class Indication:
    low: int | None
    high: int | None
    median_price_per_sqft: float | None
    basis: str


@dataclass
class Report:
    subject: Subject
    comps: list[Comp]
    pool_sold: int
    pool_active: int
    radius_miles: float
    sold_within_days: int
    indication: Indication
