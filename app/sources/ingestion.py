import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.sources.contracts import CanonicalDraw, SourceDraw
from app.sources.normalizer import normalize_source_draw
from app.sources.protocols import LotterySourceAdapter


@dataclass(frozen=True, slots=True)
class IngestionEnvelope:
    """Normalized source data plus a deterministic idempotency key."""

    draw: CanonicalDraw
    idempotency_key: str


def build_idempotency_key(source_id: str, draw: SourceDraw) -> str:
    """Build a stable key from source, draw identity and normalized groups."""
    canonical = normalize_source_draw(draw)
    payload: dict[str, Any] = {
        "source_id": source_id.strip(),
        "draw_number": canonical.draw_number,
        "draw_date": canonical.draw_date.isoformat(),
        "groups": canonical.groups,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def ingest_draws(adapter: LotterySourceAdapter) -> list[IngestionEnvelope]:
    """Fetch, normalize and fingerprint source draws without database writes."""
    source_id = adapter.source_id.strip()
    if not source_id:
        raise ValueError("source_id cannot be empty")

    envelopes: list[IngestionEnvelope] = []
    seen: set[str] = set()
    for source_draw in adapter.fetch_draws():
        normalized = normalize_source_draw(source_draw)
        key = build_idempotency_key(source_id, source_draw)
        if key in seen:
            raise ValueError(f"duplicate source draw detected: {key}")
        seen.add(key)
        envelopes.append(IngestionEnvelope(draw=normalized, idempotency_key=key))
    return envelopes
