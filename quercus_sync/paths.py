from __future__ import annotations

import re
from pathlib import Path

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")


def safe_name(value: str, fallback: str = "untitled", max_len: int = 120) -> str:
    text = (value or "").strip()
    text = _UNSAFE.sub("_", text)
    text = _SPACES.sub(" ", text).strip(" ._")
    if not text or text in {".", ".."}:
        text = fallback
    if len(text) > max_len:
        stem, suffix = _split_ext(text)
        keep = max_len - len(suffix)
        text = (stem[:keep].rstrip(" .") or fallback) + suffix
    return text


def _split_ext(name: str) -> tuple[str, str]:
    path = Path(name)
    if path.suffix and len(path.suffix) <= 8:
        return path.stem, path.suffix
    return name, ""


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while True:
        candidate = path.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def course_folder(code: str, name: str) -> str:
    code = safe_name(code, "COURSE")
    name = safe_name(name, "Untitled course")
    if name.lower().startswith(code.lower()):
        return name
    return f"{code} — {name}"
