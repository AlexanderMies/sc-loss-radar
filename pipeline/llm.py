"""Stage two: model classification on the survivors only.

Keyword rules can't tell "fire destroyed a Greer distribution center" from
"fire destroyed a home on Greer Highway". This can. It costs a fraction of a
cent per item and only runs above the threshold in scoring.yaml.

Degrades cleanly: no API key, no problem — you still get rule scores, the board
just loses the commercial/residential column. Wire the key up when you're ready.
"""

from __future__ import annotations

import json
import logging
import os

from .models import Incident

log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

PROMPT = """You are triaging news items for a commercial restoration company \
in South Carolina. They handle electronics restoration and technical recovery \
after fire, smoke, water and mold losses. They want large commercial and \
institutional losses. They do not want single-family residential.

Item:
Headline: {title}
Summary: {summary}
Source: {source}

Return ONLY a JSON object, no preamble and no markdown fences:
{{
  "property_type": "commercial" | "institutional" | "large_multifamily" | "residential" | "unclear",
  "severity": 1-5,
  "electronics_likely": true | false,
  "is_actual_loss": true | false,
  "rationale": "one sentence, under 20 words"
}}

Notes:
- "institutional" covers schools, churches, hospitals, government buildings.
- "large_multifamily" is apartment complexes and senior living — these are \
commercial-scale contents jobs, not residences.
- severity 1 is trivial, 5 is a total loss or major multi-alarm event.
- is_actual_loss is false for anniversary pieces, lawsuits, arrests, \
fundraisers, training exercises, and stories about firefighter injuries where \
no property loss is described."""


def _client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("llm: anthropic package not installed, skipping")
        return None
    return anthropic.Anthropic(api_key=api_key)


def _classify(client, incident: Incident) -> dict | None:
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": PROMPT.format(
                    title=incident.title,
                    summary=incident.summary[:800] or "(none)",
                    source=incident.source,
                ),
            }],
        )
        raw = "".join(
            block.text for block in resp.content if block.type == "text"
        ).strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as exc:
        log.warning("llm: classify failed for %s (%s)", incident.id, exc)
        return None


def enrich(incidents: list[Incident], config: dict) -> list[Incident]:
    threshold = config.get("llm_threshold", 25)
    candidates = [i for i in incidents if i.score >= threshold]

    if not candidates:
        return incidents

    client = _client()
    if client is None:
        log.info("llm: no ANTHROPIC_API_KEY set, running rules-only")
        return incidents

    log.info("llm: classifying %d of %d items", len(candidates), len(incidents))

    for incident in candidates:
        verdict = _classify(client, incident)
        if not verdict:
            continue

        incident.llm = verdict

        # Let the model move the score. It sees context the keywords can't.
        ptype = verdict.get("property_type")
        if ptype in ("commercial", "institutional"):
            incident.score += 15
        elif ptype == "large_multifamily":
            incident.score += 8
        elif ptype == "residential":
            incident.score -= 35

        severity = verdict.get("severity")
        if isinstance(severity, (int, float)):
            incident.score += (severity - 3) * 6

        if verdict.get("electronics_likely"):
            incident.score += 12

        if verdict.get("is_actual_loss") is False:
            incident.score -= 45

        incident.score = round(max(0.0, incident.score), 1)

        tiers = config.get("tiers", {})
        if incident.score >= tiers.get("priority", 60):
            incident.tier = "priority"
        elif incident.score >= tiers.get("watch", 30):
            incident.tier = "watch"
        else:
            incident.tier = "logged"

    return incidents
