from __future__ import annotations

from collections.abc import Mapping

LIFECYCLE_STATES = (
    "proposed",
    "planned",
    "construction",
    "disused",
    "abandoned",
    "demolished",
    "removed",
    "razed",
)


def detect_lifecycle(tags: Mapping[str, str]) -> list[tuple[str, str]]:
    """Return unique ``(normalized_state, raw_form)`` observations."""
    found: set[tuple[str, str]] = set()
    for key, value in tags.items():
        key_text = str(key)
        value_text = str(value)
        prefix = key_text.split(":", 1)[0].lower()
        if ":" in key_text and prefix in LIFECYCLE_STATES:
            found.add((prefix, f"{key_text}={value_text}"))
        lower_value = value_text.lower()
        if lower_value in LIFECYCLE_STATES:
            found.add((lower_value, f"{key_text}={value_text}"))
    return sorted(found)

