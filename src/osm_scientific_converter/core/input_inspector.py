from __future__ import annotations

import os
import re
import struct
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_file
from .models import InputMetadata


class InputValidationError(ValueError):
    pass


_BOUNDS_RE = re.compile(
    rb"<bounds\b[^>]*\bminlat=['\"]([^'\"]+)['\"][^>]*\bminlon=['\"]([^'\"]+)['\"][^>]*\bmaxlat=['\"]([^'\"]+)['\"][^>]*\bmaxlon=['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def _format_for(path: Path) -> str:
    lower = path.name.lower()
    if lower.endswith(".osm"):
        return "osm"
    if lower.endswith(".pbf"):
        return "pbf"
    raise InputValidationError("Input extension must be .osm, .pbf, or .osm.pbf")


def _sniff(path: Path, input_format: str) -> list[float] | None:
    with path.open("rb") as stream:
        head = stream.read(131072)
    if input_format == "osm":
        if not re.search(rb"<osm(?:\s|>)", head, re.IGNORECASE):
            raise InputValidationError("The file extension is .osm but no <osm> root was found")
        match = _BOUNDS_RE.search(head)
        if match:
            minlat, minlon, maxlat, maxlon = (float(value) for value in match.groups())
            return [minlon, minlat, maxlon, maxlat]
        return None
    if len(head) < 8:
        raise InputValidationError("PBF input is too short")
    header_size = struct.unpack(">I", head[:4])[0]
    if not (1 <= header_size <= 64 * 1024) or b"OSMHeader" not in head[: min(len(head), header_size + 4)]:
        raise InputValidationError("The file extension is .pbf but its OSM PBF header is invalid")
    return None


def inspect_input(path: str | Path) -> InputMetadata:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise InputValidationError(f"Input does not exist: {resolved}")
    if not resolved.is_file():
        raise InputValidationError(f"Input is not a regular file: {resolved}")
    if not os.access(resolved, os.R_OK):
        raise InputValidationError(f"Input is not readable: {resolved}")
    input_format = _format_for(resolved)
    bounds = _sniff(resolved, input_format)
    stat = resolved.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    return InputMetadata(
        path=str(resolved),
        sha256=sha256_file(resolved),
        format=input_format,
        size_bytes=stat.st_size,
        bounds=bounds,
        modified_time_utc=modified,
        scan_time_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
