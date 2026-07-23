"""Google News RSS.

Free, no key, no quota to speak of. The tradeoff is lag — Google takes a while
to index a local newsroom — so treat this as breadth and let the direct outlet
feeds in outlets.py carry speed.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import datetime, timezone

import feedparser

from ..models import Incident

log = logging.getLogger(__name__)

BASE = "https://news.google.com/rss/search"


def build_url(query: str, region_terms: list[str], window: str) -> str:
    parts = [query] + [f'"{t}"' for t in region_terms] + [f"when:{window}"]
    q = urllib.parse.quote_plus(" ".join(parts))
    return f"{BASE}?q={q}&hl=en-US&gl=US&ceid=US:en"


def _split_title(raw: str) -> tuple[str, str]:
    """Google News formats titles as 'Headline - Publisher'. Split on the last
    hyphen — headlines contain hyphens more often than publishers do."""
    if " - " in raw:
        head, _, pub = raw.rpartition(" - ")
        return head.strip(), pub.strip()
    return raw.strip(), "Google News"


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return datetime.now(timezone.utc)


def fetch(config: dict) -> list[Incident]:
    defaults = config.get("defaults", {})
    window = defaults.get("window", "2d")
    region_terms = defaults.get("region_terms", ["South Carolina"])

    incidents: list[Incident] = []

    for spec in config.get("queries", []):
        if not spec.get("enabled", True):
            continue

        query = spec["q"]
        url = build_url(query, region_terms, spec.get("window", window))

        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            log.warning("google_news: %r failed: %s", query, exc)
            continue

        if getattr(feed, "bozo", False) and not feed.entries:
            log.warning("google_news: %r returned nothing parseable", query)
            continue

        for entry in feed.entries:
            title, publisher = _split_title(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            if not title or not link:
                continue

            incidents.append(
                Incident(
                    title=title,
                    url=link,
                    source=publisher,
                    source_type="google_news",
                    published=_parse_date(entry),
                    summary=getattr(entry, "summary", "")[:600],
                    category=spec.get("category", "fire"),
                    query=query,
                )
            )

        log.info("google_news: %-45s %3d items", query[:45], len(feed.entries))
        time.sleep(1.0)  # be polite; Google will throttle a tight loop

    return incidents
