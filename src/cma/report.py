"""Render a CMA as Slack mrkdwn that is also readable in a terminal."""

from __future__ import annotations

import json
from datetime import date

from cma.models import Comp, Report, Subject


def render_text(report: Report) -> str:
    subject = report.subject
    sold = [comp for comp in report.comps if comp.group == "sold"]
    active = [comp for comp in report.comps if comp.group == "active"]
    lines = [
        f"*CMA · {subject.address}*",
        f"Within { _miles(report.radius_miles) } · sold in the last {_window(report.sold_within_days)} and homes on the market now",
        "",
        "*Subject*",
        _subject_facts(subject),
        "",
        "*Comp-based value band*",
        _indication(report),
        "This is a comp set, not an appraisal.",
        "",
        (
            f"*Pool:* {report.pool_sold} sold and {report.pool_active} active within "
            f"{_miles(report.radius_miles)}. Showing {len(sold)} sold and {len(active)} active."
        ),
        "",
        "*Sold*",
    ]
    lines.extend(_comp_lines(sold, subject) or ["None within 1 mile in this window."])
    lines.append("")
    lines.append("*On the market*")
    lines.extend(_comp_lines(active, subject) or ["None on the market within 1 mile."])
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: Report) -> str:
    subject = report.subject
    payload = {
        "subject": {
            "address": subject.address,
            "matched_address": subject.matched_address,
            "latitude": subject.latitude,
            "longitude": subject.longitude,
            "zip": subject.zip_code,
            "city": subject.city,
            "state": subject.state,
            "beds": subject.beds,
            "baths": subject.baths,
            "sqft": subject.sqft,
            "year_built": subject.year_built,
            "facts_source": subject.facts_source,
        },
        "radius_miles": report.radius_miles,
        "sold_within_days": report.sold_within_days,
        "pool": {"sold": report.pool_sold, "active": report.pool_active},
        "indication": {
            "low": report.indication.low,
            "high": report.indication.high,
            "median_price_per_sqft": report.indication.median_price_per_sqft,
            "basis": report.indication.basis,
        },
        "comps": [_comp_json(comp) for comp in report.comps],
    }
    return json.dumps(payload, indent=2) + "\n"


def _subject_facts(subject: Subject) -> str:
    parts = [
        _count(subject.beds, "bd"),
        _count(subject.baths, "ba"),
        _sqft(subject.sqft),
        f"built {subject.year_built}" if subject.year_built else None,
    ]
    facts = " · ".join(part for part in parts if part)
    if not facts:
        return "Beds, baths, and square footage were not on a listing or assessment record. Comps are ranked by distance."
    source = f" Facts from {subject.facts_source}." if subject.facts_source else ""
    if subject.facts_source and "assessment" in subject.facts_source:
        source += " Assessment value is not a market value."
    return facts + "." + source if not facts.endswith(".") else facts + source


def _indication(report: Report) -> str:
    indication = report.indication
    if indication.low is None or indication.high is None:
        return indication.basis[:1].upper() + indication.basis[1:] + "."
    band = _money(indication.low) if indication.low == indication.high else f"{_money(indication.low)} – {_money(indication.high)}"
    if indication.median_price_per_sqft is not None and report.subject.sqft:
        midpoint = round(indication.median_price_per_sqft * report.subject.sqft / 1000.0) * 1000
        return (
            f"Median {_money(midpoint)} ({_money(round(indication.median_price_per_sqft))}/sf). "
            f"Sold-comp range {band}."
        )
    return f"{band}. Based on {indication.basis}."


def _comp_lines(comps: list[Comp], subject: Subject) -> list[str]:
    lines: list[str] = []
    for index, comp in enumerate(comps, start=1):
        price = _money(comp.price)
        when = ""
        if comp.group == "sold" and comp.sold_date is not None:
            when = f" on {comp.sold_date.strftime('%b')} {comp.sold_date.day}, {comp.sold_date.year}"
        status = "Closed" if comp.group == "sold" else comp.mls_status
        facts = " · ".join(
            part
            for part in (
                _count(comp.beds, "bd"),
                _count(comp.baths, "ba"),
                _sqft(comp.sqft),
                _ppsf(comp),
                f"{comp.dom} days on market" if comp.dom is not None else None,
            )
            if part
        )
        lines.append(
            f"{index}. *{comp.address}* · {_distance(comp.distance_miles)}"
        )
        lines.append(f"   {status} {price}{when}" + (f" · {facts}" if facts else ""))
        note = _difference(subject, comp)
        if note:
            lines.append(f"   {note}")
        if comp.url:
            lines.append(f"   {comp.url}")
    return lines


def _difference(subject: Subject, comp: Comp) -> str:
    notes: list[str] = []
    if subject.sqft and comp.sqft:
        delta = (comp.sqft - subject.sqft) / subject.sqft
        if abs(delta) >= 0.08:
            notes.append(f"{abs(delta):.0%} {'larger' if delta > 0 else 'smaller'}")
    if subject.beds is not None and comp.beds is not None and subject.beds != comp.beds:
        notes.append(f"{_count(comp.beds, 'bd')} vs subject {_count(subject.beds, 'bd')}")
    return ", ".join(notes)


def _comp_json(comp: Comp) -> dict:
    return {
        "group": comp.group,
        "address": comp.address,
        "mls_status": comp.mls_status,
        "price": comp.price,
        "beds": comp.beds,
        "baths": comp.baths,
        "sqft": comp.sqft,
        "year_built": comp.year_built,
        "distance_miles": round(comp.distance_miles, 3),
        "sold_date": comp.sold_date.isoformat() if isinstance(comp.sold_date, date) else None,
        "days_on_market": comp.dom,
        "price_per_sqft": round(comp.price / comp.sqft) if comp.sqft else None,
        "url": comp.url,
    }


def _money(amount: float | int) -> str:
    return f"${int(round(amount)):,}"


def _sqft(value: int | None) -> str | None:
    if not value:
        return None
    return f"{value:,} sf"


def _count(value: float | None, label: str) -> str | None:
    if value is None:
        return None
    if float(value).is_integer():
        shown = str(int(value))
    else:
        shown = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{shown} {label}"


def _ppsf(comp: Comp) -> str | None:
    if not comp.sqft:
        return None
    return f"{_money(round(comp.price / comp.sqft))}/sf"


def _distance(miles: float) -> str:
    if miles < 0.01:
        return "<0.01 mi"
    return f"{miles:.2f} mi"


def _miles(radius: float) -> str:
    if float(radius).is_integer():
        unit = "mile" if int(radius) == 1 else "miles"
        return f"{int(radius)} {unit}"
    return f"{radius:.1f} miles"


def _window(days: int) -> str:
    if days == 365:
        return "12 months"
    if days % 30 == 0:
        months = days // 30
        return f"{months} month" if months == 1 else f"{months} months"
    return f"{days} days"
