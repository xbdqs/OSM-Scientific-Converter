from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_PATH_IN_TEXT = re.compile(r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/][^\r\n\t\"']+")


def portable_project_path(path: str | Path, project: str | Path, *, external_label: str = "external") -> str:
    """Return a portable project-relative path without exposing an external parent."""
    resolved = Path(path).expanduser().resolve()
    root = Path(project).expanduser().resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return f"<{external_label}>/{resolved.name}"
    value = relative.as_posix()
    return value if value else "."


def portable_profile_source(source: str) -> str:
    if source.startswith("builtin:"):
        return source
    path = Path(source)
    return f"custom:{path.name}"


def _looks_absolute(value: str) -> bool:
    return bool(_WINDOWS_ABSOLUTE.match(value)) or value.startswith("\\\\") or value.startswith("/")


def sanitize_paths(value: Any) -> Any:
    """Recursively redact absolute paths before a report enters a feedback ZIP."""
    if isinstance(value, dict):
        return {str(key): sanitize_paths(child) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize_paths(child) for child in value]
    if isinstance(value, str) and _looks_absolute(value):
        normalized = value.replace("\\", "/").rstrip("/")
        return f"<redacted-path>/{normalized.rsplit('/', 1)[-1]}"
    return value


def contains_absolute_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(contains_absolute_path(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_absolute_path(child) for child in value)
    return isinstance(value, str) and _looks_absolute(value)


def redact_absolute_paths_in_text(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        normalized = match.group(0).replace("\\", "/").rstrip(" /,;)")
        return f"<redacted-path>/{normalized.rsplit('/', 1)[-1]}"

    return _WINDOWS_PATH_IN_TEXT.sub(replace, text)
