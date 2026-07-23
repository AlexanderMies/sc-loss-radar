"""Stage one: cheap deterministic scoring.

Runs on everything. Fast, free, and explainable — every score comes with the
list of signals that produced it, so when the board shows you something dumb
you can see exactly which rule fired and go fix the weight.

Stage two (llm.py) only sees what survives this.
"""

from __future__ import annotations

import logging
import re

from .models import Incident

log = logging.getLogger(__name__)


def _matches(text: str, terms: list[str]) -> list[str]:
    """Whole-phrase matching. Substring matching would let 'fire' inside
    'firearm' or 'wildfire' fire the wrong rule."""
    hits = []
    for term in terms:
        if re.search(rf"\b{re.escape(term.lower())}\b", text):
            hits.append(term)
    return hits


def _freshness_penalty(age_hours: float, config: dict) -> float:
    fresh = config.get("freshness", {})
    grace = fresh.get("full_credit_hours", 6)
    rate = fresh.get("penalty_per_hour", 1.5)
    cap = fresh.get("max_penalty", 30)

    if age_hours <= grace:
        return 0.0
    return min(cap, (age_hours - grace) * rate)


def score_one(incident: Incident, config: dict) -> Incident:
    text = incident.text
    total = 0.0
    signals: list[str] = []

    for name, rule in config.get("signals", {}).items():
        hits = _matches(text, rule.get("terms", []))
        if hits:
            total += rule.get("weight", 0)
            signals.append(f"{name}:{hits[0]}")

    for name, rule in config.get("penalties", {}).items():
        hits = _matches(text, rule.get("terms", []))
        if hits:
            total += rule.get("weight", 0)   # weights are negative
            signals.append(f"-{name}:{hits[0]}")

    # Broad coverage means it's a real event, not a two-line brief.
    if incident.cluster_size >= 3:
        total += 8
        signals.append(f"coverage:{incident.cluster_size}_outlets")

    # Weather alerts are territory intelligence, not a named loss. Cap them so
    # they inform without crowding out confirmed incidents.
    if incident.source_type == "nws":
        total = min(total, 45)
        signals.append("nws:capped")

    penalty = _freshness_penalty(incident.age_hours, config)
    if penalty:
        total -= penalty
        signals.append(f"-stale:{incident.age_hours:.0f}h")

    incident.score = round(max(0.0, total), 1)
    incident.signals = signals

    tiers = config.get("tiers", {})
    if incident.score >= tiers.get("priority", 60):
        incident.tier = "priority"
    elif incident.score >= tiers.get("watch", 30):
        incident.tier = "watch"
    else:
        incident.tier = "logged"

    return incident


def score_all(incidents: list[Incident], config: dict) -> list[Incident]:
    scored = [score_one(i, config) for i in incidents]
    counts = {t: sum(1 for i in scored if i.tier == t)
              for t in ("priority", "watch", "logged")}
    log.info("score: %s", counts)
    return scored
