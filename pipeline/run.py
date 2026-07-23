"""Collect -> place -> dedupe -> score -> classify -> write.

Run locally:   python -m pipeline.run
Rules only:    python -m pipeline.run --no-llm
Wider net:     python -m pipeline.run --keep-all
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import dedupe, geo, llm, score
from .models import Incident
from .sources import google_news, nws, outlets

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"

# leads.json lives inside docs/ because GitHub Pages only serves files from the
# publish directory. Anything in a sibling folder 404s at runtime — an easy
# half-hour to lose if you haven't hit it before.
SITE_DATA = ROOT / "docs" / "data"
LEADS = SITE_DATA / "leads.json"

# The archive isn't served — it's the backtesting record, kept out of the site.
ARCHIVE = ROOT / "data" / "archive"

RETENTION_DAYS = 10   # how much history the board carries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-24s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run")


def load(name: str) -> dict:
    with open(CONFIG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def collect() -> list[Incident]:
    queries = load("queries.yaml")
    feeds = load("outlets.yaml")

    incidents: list[Incident] = []
    for label, fetcher, cfg in (
        ("google_news", google_news.fetch, queries),
        ("outlets", outlets.fetch, feeds),
        ("nws", nws.fetch, feeds),
    ):
        try:
            found = fetcher(cfg)
            log.info("collect: %s -> %d", label, len(found))
            incidents.extend(found)
        except Exception as exc:
            # One bad source shouldn't cost you the whole run.
            log.error("collect: %s failed entirely (%s)", label, exc)

    return incidents


def place(incidents: list[Incident], keep_all: bool) -> list[Incident]:
    kept = []
    for incident in incidents:
        city, county, in_sc = geo.locate(f"{incident.title} {incident.summary}")
        if not in_sc and not keep_all:
            continue
        incident.place = incident.place or city
        incident.county = county
        kept.append(incident)

    log.info("place: %d of %d located in SC", len(kept), len(incidents))
    return kept


def carry_forward(incidents: list[Incident]) -> list[Incident]:
    """Preserve first_seen across runs and keep recent history on the board.

    Without this, every run resets the clock and you can't tell a lead you saw
    twenty minutes ago from one that just broke.
    """
    if not LEADS.exists():
        return incidents

    try:
        previous = json.loads(LEADS.read_text(encoding="utf-8"))
    except Exception:
        return incidents

    seen = {row["id"]: row for row in previous.get("leads", [])}
    current_ids = set()

    for incident in incidents:
        current_ids.add(incident.id)
        prior = seen.get(incident.id)
        if prior and prior.get("first_seen"):
            try:
                incident.first_seen = datetime.fromisoformat(prior["first_seen"])
            except ValueError:
                pass

    # Keep still-recent leads that fell out of the source windows.
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    revived = 0
    for row in previous.get("leads", []):
        if row["id"] in current_ids:
            continue
        try:
            published = datetime.fromisoformat(row["published"])
        except (ValueError, KeyError):
            continue
        if published < cutoff:
            continue

        incidents.append(
            Incident(
                title=row["title"],
                url=row["url"],
                source=row.get("source", ""),
                source_type=row.get("source_type", "outlet"),
                published=published,
                summary=row.get("summary", ""),
                category=row.get("category", "fire"),
                place=row.get("place", ""),
                county=row.get("county", ""),
                query=row.get("query", ""),
                first_seen=datetime.fromisoformat(
                    row.get("first_seen", row["published"])
                ),
                cluster_size=row.get("cluster_size", 1),
                related=row.get("related", []),
                llm=row.get("llm"),
            )
        )
        revived += 1

    if revived:
        log.info("carry_forward: kept %d recent leads from prior run", revived)
    return incidents


def write(incidents: list[Incident]) -> None:
    incidents.sort(key=lambda i: (i.score, i.published), reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "total": len(incidents),
            "priority": sum(1 for i in incidents if i.tier == "priority"),
            "watch": sum(1 for i in incidents if i.tier == "watch"),
            "logged": sum(1 for i in incidents if i.tier == "logged"),
        },
        "leads": [i.to_dict() for i in incidents],
    }

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    LEADS.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Monthly archive. This is what you'll backtest scoring changes against —
    # don't skip it, it's the only record of what the board actually showed.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m")
    archive_path = ARCHIVE / f"{stamp}.json"
    existing = []
    if archive_path.exists():
        try:
            existing = json.loads(archive_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    known = {row["id"] for row in existing}
    existing.extend(r for r in payload["leads"] if r["id"] not in known)
    archive_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    log.info("write: %s", payload["counts"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true",
                        help="skip the model pass, rules only")
    parser.add_argument("--keep-all", action="store_true",
                        help="don't filter to South Carolina (for debugging)")
    args = parser.parse_args()

    scoring = load("scoring.yaml")

    incidents = collect()
    incidents = place(incidents, keep_all=args.keep_all)
    incidents = carry_forward(incidents)
    incidents = dedupe.cluster(incidents)
    incidents = score.score_all(incidents, scoring)

    if not args.no_llm:
        incidents = llm.enrich(incidents, scoring)

    write(incidents)


if __name__ == "__main__":
    main()
