"""Cluster coverage of the same event.

One warehouse fire will hit eight outlets inside two hours. Without this you
score, LLM-classify and display it eight times, and your board looks busy while
telling you about one job.

We keep the earliest-published copy as the canonical record — that's the one
that told you first — and attach the rest as `related` so you can see how much
coverage an event is drawing. Broad coverage is itself a severity signal.
"""

from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

from .models import Incident

log = logging.getLogger(__name__)

# Stripped before comparison so "BREAKING: Warehouse fire in Greer" and
# "Warehouse fire in Greer, crews on scene" recognize each other.
NOISE = re.compile(
    r"\b(breaking|update|updated|watch|live|video|photos|developing|"
    r"crews on scene|officials say|police say|report)\b[:\s-]*",
    re.IGNORECASE,
)

SIMILARITY_THRESHOLD = 82   # 0-100. Lower = more aggressive merging.
TIME_WINDOW_HOURS = 36      # only cluster things close in time


def _normalize(title: str) -> str:
    cleaned = NOISE.sub("", title)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _same_event(a: Incident, b: Incident) -> bool:
    gap = abs((a.published - b.published).total_seconds()) / 3600
    if gap > TIME_WINDOW_HOURS:
        return False

    score = fuzz.token_set_ratio(_normalize(a.title), _normalize(b.title))

    # Same town mentioned in both? Lower the bar — local specificity is strong
    # evidence two stories are about the same incident.
    if a.place and a.place == b.place:
        return score >= SIMILARITY_THRESHOLD - 10

    return score >= SIMILARITY_THRESHOLD


def cluster(incidents: list[Incident]) -> list[Incident]:
    """Collapse near-duplicate coverage into one Incident each."""
    ordered = sorted(incidents, key=lambda i: i.published)
    canonical: list[Incident] = []

    for incident in ordered:
        match = next((c for c in canonical if _same_event(c, incident)), None)

        if match is None:
            canonical.append(incident)
            continue

        match.cluster_size += 1
        match.related.append(
            {
                "title": incident.title,
                "url": incident.url,
                "source": incident.source,
            }
        )
        # Prefer a real outlet byline over a Google News aggregation for the
        # canonical link — fewer redirects, better article text.
        if match.source_type == "google_news" and incident.source_type == "outlet":
            match.url = incident.url
            match.source = incident.source
            match.source_type = "outlet"
        # Keep the richest summary we've seen.
        if len(incident.summary) > len(match.summary):
            match.summary = incident.summary

    collapsed = len(incidents) - len(canonical)
    log.info("dedupe: %d items -> %d events (%d merged)",
             len(incidents), len(canonical), collapsed)
    return canonical
