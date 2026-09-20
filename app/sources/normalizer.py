from app.sources.contracts import CanonicalDraw, SourceDraw


def normalize_source_draw(source_draw: SourceDraw) -> CanonicalDraw:
    """Normalize source values while preserving provenance and raw payload."""
    groups: dict[str, tuple[str, ...]] = {}
    for group_code, values in source_draw.groups.items():
        normalized_code = group_code.strip().lower()
        if not normalized_code:
            raise ValueError("group_code cannot be empty")

        normalized_values = tuple(str(value).strip() for value in values)
        if any(not value for value in normalized_values):
            raise ValueError(f"group {normalized_code!r} contains an empty value")
        if len(normalized_values) != len(set(normalized_values)):
            raise ValueError(f"group {normalized_code!r} contains duplicate values")
        groups[normalized_code] = normalized_values

    if len(groups) != len(source_draw.groups):
        raise ValueError("group codes collide after normalization")

    return CanonicalDraw(
        draw_number=source_draw.draw_number.strip(),
        draw_date=source_draw.draw_date,
        draw_datetime=source_draw.draw_datetime,
        groups=groups,
        metadata=source_draw.metadata,
        raw_payload=source_draw.raw_payload,
    )
