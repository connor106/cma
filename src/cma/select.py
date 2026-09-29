"""Pick 4 or 5 comps, mixing recent sales with homes on the market."""

from __future__ import annotations

import statistics
from datetime import date

from cma.models import Comp, Indication, Subject

SOLD_TARGET = 3
ACTIVE_TARGET = 2
COMP_TARGET = 5


def similarity(comp: Comp, subject: Subject, today: date) -> float:
    """Lower scores are closer matches. Distance and size dominate."""
    score = comp.distance_miles * 20.0
    if subject.beds is not None and comp.beds is not None:
        score += abs(comp.beds - subject.beds) * 2.0
    elif subject.beds is not None:
        score += 2.0
    if subject.baths is not None and comp.baths is not None:
        score += abs(comp.baths - subject.baths) * 1.0
    if subject.sqft and comp.sqft:
        score += abs(comp.sqft - subject.sqft) / subject.sqft * 6.0
    elif subject.sqft:
        score += 5.0
    if comp.group == "sold":
        if comp.sold_date is None:
            score += 1.5
        else:
            age = max(0, (today - comp.sold_date).days)
            score += min(age, 365) / 365 * 1.5
    return score


def _prefer_known_size(comps: list[Comp], keep: int) -> list[Comp]:
    """Ignore missing square footage when enough sized comps are already in range."""
    sized = [comp for comp in comps if comp.sqft]
    if len(sized) >= keep:
        return sized
    return comps


def select_comps(
    sold: list[Comp],
    active: list[Comp],
    subject: Subject,
    *,
    today: date,
) -> list[Comp]:
    """Choose up to three sold comps and two active comps, then fill to five."""
    sold = _prefer_known_size(sold, SOLD_TARGET)
    active = _prefer_known_size(active, ACTIVE_TARGET)
    sold_ranked = sorted(sold, key=lambda comp: similarity(comp, subject, today))
    active_ranked = sorted(active, key=lambda comp: similarity(comp, subject, today))
    picked = sold_ranked[:SOLD_TARGET] + active_ranked[:ACTIVE_TARGET]
    if len(picked) < COMP_TARGET:
        leftovers = sold_ranked[SOLD_TARGET:] + active_ranked[ACTIVE_TARGET:]
        leftovers.sort(key=lambda comp: similarity(comp, subject, today))
        picked.extend(leftovers[: COMP_TARGET - len(picked)])
    sold_picked = [comp for comp in picked if comp.group == "sold"]
    active_picked = [comp for comp in picked if comp.group == "active"]
    sold_picked.sort(key=lambda comp: similarity(comp, subject, today))
    active_picked.sort(key=lambda comp: similarity(comp, subject, today))
    return (sold_picked + active_picked)[:COMP_TARGET]


def indicate_value(subject: Subject, comps: list[Comp]) -> Indication:
    """Build a value band from the selected sold comps' price per square foot."""
    sold = [comp for comp in comps if comp.group == "sold" and comp.sqft and comp.sqft > 0]
    if subject.sqft and sold:
        prices = [comp.price / comp.sqft for comp in sold]
        median = statistics.median(prices)
        low = round_to_thousand(min(prices) * subject.sqft)
        high = round_to_thousand(max(prices) * subject.sqft)
        if low > high:
            low, high = high, low
        return Indication(
            low=low,
            high=high,
            median_price_per_sqft=median,
            basis="sold comps below, applied to the subject square footage",
        )
    priced = [comp.price for comp in comps if comp.group == "sold"]
    if not priced:
        return Indication(
            low=None,
            high=None,
            median_price_per_sqft=None,
            basis="not enough recent sales with square footage to price the subject",
        )
    return Indication(
        low=round_to_thousand(min(priced)),
        high=round_to_thousand(max(priced)),
        median_price_per_sqft=None,
        basis="sold prices only, because the subject square footage is missing",
    )


def round_to_thousand(amount: float) -> int:
    return int(round(amount / 1000.0) * 1000)
