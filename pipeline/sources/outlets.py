"""Direct newsroom RSS feeds.

These are the fast path. An outlet posts to its own feed well before Google
indexes it, and on a lead that rots in hours that gap is the whole game.

Outlet feeds are unfiltered — everything from city council to high school
football — so we keep only items that trip a loss-related keyword before
handing them downstream.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import feedparser
import httpx

from ..models import Incident

log = logging.getLogger(__name__)

# Cheap prefilter. Deliberately loose — the scorer does the real work, this
# just avoids paying dedupe and geo costs on obvious non-events.
RELEVANT = [
    "fire", "blaze", "smoke", "burn", "flame",
    "water damage", "flood", "sprinkler", "burst pipe", "water main",
    "mold", "storm damage", "roof collapse", "evacuat", "damage",
]

CATEGORY_HINTS = [
    ("mold", "mold"),
    ("flood", "water"),
    ("water damage", "water"),
    ("sprinkler", "water"),
    ("burst pipe", "water"),
    ("water main", "water"),
    ("storm", "storm"),
    ("hurricane", "storm"),
    ("tornado", "storm"),
]

HEADERS = {
    "User-Agent": "sc-loss-radar/1.0 (+https://github.com/)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _categorize(text: str) -> str:
    lowered = text.lower()
    for needle, category in CATEGORY_HINTS:
        if needle in lowered:
            return category
    return "fire"


def _is_relevant(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in RELEVANT)


def fetch(config: dict, timeout: float = 20.0) -> list[Incident]:
    incidents: list[Incident] = []

    with httpx.Client(
        headers=HEADERS, timeout=timeout, follow_redirects=True
    ) as client:
        for outlet in config.get("outlets", []):
            name = outlet["name"]
            try:
                resp = client.get(outlet["url"])
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
            except Exception as exc:
                # A dead feed shouldn't take down the run. Log and move on —
                # but do check these logs, a 404 here is silent data loss.
                log.warning("outlets: %s unreachable (%s)", name, exc)
                continue

            kept = 0
            for entry in feed.entries:
                title = getattr(entry, "title", "").strip()
                link = getattr(entry, "link", "").strip()
                summary = getattr(entry, "summary", "")[:600]
                if not title or not link:
                    continue

                blob = f"{title} {summary}"
                if not _is_relevant(blob):
                    continue

                incidents.append(
                    Incident(
                        title=title,
                        url=link,
                        source=name,
                        source_type="outlet",
                        published=_parse_date(entry),
                        summary=summary,
                        category=_categorize(blob),
                        place="",
                        query=f"outlet:{name}",
                    )
                )
                kept += 1

            log.info(
                "outlets: %-24s %3d items, %2d relevant",
                name, len(feed.entries), kept,
            )

    return incidents
