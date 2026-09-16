from __future__ import annotations

import os
import re
from collections.abc import Iterator
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


def clip_path(path: Path, limit: int = 240, keep_prefix: Path | None = None) -> Path:
    """Keep Windows paths under MAX_PATH by shortening the leaf first, not the course folder."""
    path = Path(path)
    absolute = path if path.is_absolute() else Path.cwd() / path
    parts = list(absolute.parts)
    prefix_len = 0
    if keep_prefix is not None:
        prefix = keep_prefix if keep_prefix.is_absolute() else Path.cwd() / keep_prefix
        prefix_parts = list(prefix.parts)
        if parts[: len(prefix_parts)] == prefix_parts:
            prefix_len = len(prefix_parts)
    while len(str(Path(*parts))) > limit:
        idx = None
        for i in range(len(parts) - 1, 0, -1):
            if i < prefix_len:
                break
            if len(parts[i]) > 8:
                idx = i
                break
        if idx is None:
            break
        stem, suffix = Path(parts[idx]).stem, Path(parts[idx]).suffix
        keep = max(8, len(stem) - 12)
        shortened = (stem[:keep].rstrip(" .") or "item") + suffix
        if shortened == parts[idx]:
            keep = max(4, len(stem) - 1)
            shortened = (stem[:keep].rstrip(" .") or "item") + suffix
            if shortened == parts[idx]:
                break
        parts[idx] = shortened
    return Path(*parts)


def course_folder(code: str, name: str) -> str:
    code = safe_name(code, "COURSE")
    name = safe_name(name, "Untitled course")
    if name.lower().startswith(code.lower()):
        return name
    return f"{code} — {name}"


def long_path(path: Path) -> Path:
    """Windows MAX_PATH bypass so OneDrive copies and deletes still work."""
    text = str(path)
    if text.startswith("\\\\?\\"):
        return Path(text)
    absolute = os.path.abspath(text)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def strip_long_prefix(path: Path) -> Path:
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        return Path("\\\\" + text[8:])
    if text.startswith("\\\\?\\"):
        return Path(text[4:])
    return Path(text)


def iter_files(root: Path) -> Iterator[Path]:
    start = long_path(root)
    if not start.exists():
        return
    for dirpath, _dirnames, filenames in os.walk(start):
        for name in filenames:
            yield strip_long_prefix(Path(dirpath) / name)
