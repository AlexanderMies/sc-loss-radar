"""Common schema every source normalizes into."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Incident:
    """One potential loss event.

    Sources produce these in whatever shape they can; everything downstream
    (dedupe, scoring, the board) only ever sees this.
    """

    title: str
    url: str
    source: str                      # "WIS News 10", "Google News", "NWS"
    source_type: str                 # "outlet" | "google_news" | "nws"
    published: datetime
    summary: str = ""
    category: str = "fire"           # fire | water | mold | storm
    place: str = ""                  # best-guess city/town
    county: str = ""
    query: str = ""                  # which query surfaced it, for source stats

    # Filled in downstream
    first_seen: datetime = field(default_factory=_now)
    score: float = 0.0
    tier: str = "logged"             # priority | watch | logged
    signals: list[str] = field(default_factory=list)
    llm: dict[str, Any] | None = None
    cluster_size: int = 1
    related: list[dict[str, str]] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Stable ID from the URL, so the same story keeps its identity
        across runs and we can carry first_seen forward."""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:12]

    @property
    def text(self) -> str:
        """Everything scoreable, lowercased once."""
        return f"{self.title} {self.summary}".lower()

    @property
    def age_hours(self) -> float:
        delta = _now() - self.published
        return max(0.0, delta.total_seconds() / 3600)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        d["published"] = self.published.isoformat()
        d["first_seen"] = self.first_seen.isoformat()
        d["age_hours"] = round(self.age_hours, 1)
        return d
