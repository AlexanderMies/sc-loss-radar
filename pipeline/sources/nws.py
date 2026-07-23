"""National Weather Service active alerts for South Carolina.

api.weather.gov is free, keyless, and public domain. These fire *before* any
news story exists, which makes them the earliest signal in the whole system —
a flash flood warning over an industrial corridor is a water-loss forecast.

Treat these as territory intelligence rather than individual leads. An alert
tells you where to point attention over the next 24 hours; it doesn't name a
building. Scored lower than a confirmed loss for that reason.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..models import Incident

log = logging.getLogger(__name__)

HEADERS = {
    # weather.gov asks for a contact address in the UA. Put a real one here.
    "User-Agent": "sc-loss-radar/1.0 (contact@example.com)",
    "Accept": "application/geo+json",
}


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def fetch(config: dict, timeout: float = 20.0) -> list[Incident]:
    nws = config.get("nws", {})
    if not nws.get("enabled", False):
        return []

    allowlist = set(nws.get("event_allowlist", []))

    try:
        with httpx.Client(headers=HEADERS, timeout=timeout) as client:
            resp = client.get(nws["url"])
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        log.warning("nws: fetch failed (%s)", exc)
        return []

    incidents: list[Incident] = []

    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        event = props.get("event", "")
        if allowlist and event not in allowlist:
            continue

        areas = props.get("areaDesc", "")
        headline = props.get("headline") or f"{event} — {areas}"

        category = "storm"
        if "Flood" in event:
            category = "water"

        incidents.append(
            Incident(
                title=headline,
                url=props.get("uri") or props.get("@id", nws["url"]),
                source="National Weather Service",
                source_type="nws",
                published=_parse_iso(props.get("sent") or props.get("effective")),
                summary=(props.get("description") or "")[:600],
                category=category,
                place=areas.split(";")[0].strip() if areas else "",
                query="nws:alerts",
            )
        )

    log.info("nws: %d alerts matched allowlist", len(incidents))
    return incidents
