from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from html import escape, unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from quercus_sync.paths import iter_files, safe_name

# Canvas page HTML uses /files/:id, /courses/:id/files/:id, and data-file-id.
_FILE_ID_PATTERNS = (
    re.compile(r"/api/v1/files/(\d+)", re.I),
    re.compile(r"/files/(\d+)", re.I),
    re.compile(r"data-file-id=[\"'](\d+)[\"']", re.I),
    re.compile(r"data-api-endpoint=[\"'][^\"']*/files/(\d+)", re.I),
)
_PAGE_SLUG = re.compile(
    r"(?:/courses/\d+)?/(?:pages|wiki)/([^\"'/?#\s<>]+)",
    re.I,
)
_HREF_OR_SRC = re.compile(
    r"""(?:href|src)\s*=\s*["']([^"']+)["']""",
    re.I,
)
_SKIP_URL = re.compile(r"^(#|javascript:|mailto:|tel:|data:|blob:)", re.I)
_CANVAS_FILE_OR_PAGE = re.compile(r"/files/\d+|/(?:pages|wiki)/", re.I)
_ATTR_URL = re.compile(
    r'(?P<pre>(?:href|src)\s*=\s*)(?P<q>["\'])(?P<url>.*?)(?P=q)',
    re.I | re.S,
)
_HREF_BLIND = re.compile(r'((?:href|src)\s*=\s*["\'])(.*?)(["\'])', re.I | re.S)
_TITLE_ATTR = re.compile(r'\b(?:title|alt)\s*=\s*["\']([^"\']+)["\']', re.I)
_SLUG_META = re.compile(r"<span>\s*Slug\s*</span>\s*<strong>([^<]+)</strong>", re.I)
_FILE_ID_IN_URL = re.compile(r"/files/(\d+)", re.I)
_PAGE_SLUG_IN_URL = re.compile(r"/(?:pages|wiki)/([^/?#]+)", re.I)
_INDEX_SKIP = {"_manifest.json", "_file_index.json", "links.md"}


def canvas_file_ids(html: str | None) -> set[int]:
    """File IDs a student can already click in Canvas HTML (front page, syllabus, etc.)."""
    if not html:
        return set()
    found: set[int] = set()
    for pattern in _FILE_ID_PATTERNS:
        for match in pattern.finditer(html):
            found.add(int(match.group(1)))
    return found


def canvas_page_slugs(html: str | None) -> set[str]:
    """Wiki page slugs linked from Canvas HTML (home, modules, announcements)."""
    if not html:
        return set()
    slugs: set[str] = set()
    for match in _PAGE_SLUG.finditer(html):
        slug = unquote(match.group(1)).strip().strip("/")
        if slug and slug not in {".", ".."}:
            slugs.add(slug)
    return slugs


def html_external_links(html: str | None) -> list[tuple[str, str]]:
    """http(s) links that are not Canvas files or wiki pages (YouTube, Zoom, Play, Piazza…)."""
    if not html:
        return []
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in _HREF_OR_SRC.finditer(html):
        raw = match.group(1).strip()
        if not raw or _SKIP_URL.search(raw) or _CANVAS_FILE_OR_PAGE.search(raw):
            continue
        if not re.match(r"^https?://", raw, re.I):
            continue
        parsed = urlparse(raw)
        if not parsed.netloc:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        found.append((raw, parsed.netloc))
    return found


def html_document(title: str, body_html: str, meta: dict[str, Any] | None = None) -> str:
    rows = ""
    if meta:
        items = "".join(
            f"<li><span>{escape(str(k))}</span><strong>{escape(str(v))}</strong></li>"
            for k, v in meta.items()
            if v not in (None, "")
        )
        rows = f'<ul class="meta">{items}</ul>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0; background: #f7f1e6; color: #1c1914;
      font: 17px/1.55 "Iowan Old Style", "Palatino Linotype", Palatino, serif;
    }}
    main {{ max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.8rem; letter-spacing: -0.03em; margin: 0 0 0.75rem; }}
    .meta {{ list-style: none; padding: 0; margin: 0 0 1.5rem; color: #5c564c; font-size: 0.92rem; }}
    .meta li {{ display: flex; gap: 0.75rem; }}
    .meta span {{ min-width: 7rem; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.72rem; padding-top: 0.2rem; }}
    a {{ color: #8a3b12; }}
    img {{ max-width: 100%; }}
    pre, code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88em; }}
    .canvas-page {{ background: #fffdf8; border: 1px solid #e4d9c6; padding: 1.25rem 1.4rem; border-radius: 10px; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    {rows}
    <article class="canvas-page">{body_html or "<p><em>No body text on Quercus.</em></p>"}</article>
  </main>
</body>
</html>
"""


def iso(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def html_without_urls(html: str) -> str:
    """Compare archived pages without caring whether hrefs are still on Quercus."""
    return _HREF_BLIND.sub(r"\1\3", html)


def local_href(from_file: Path, to_file: Path) -> str:
    rel = os.path.relpath(os.path.abspath(str(to_file)), start=os.path.dirname(os.path.abspath(str(from_file))))
    return "/".join(quote(part, safe=".$~-") for part in Path(rel).as_posix().split("/"))


def rewrite_local_links(
    html: str,
    html_path: Path,
    *,
    file_by_id: dict[int, Path],
    page_by_slug: dict[str, Path],
    files_by_name: dict[str, list[Path]],
) -> str:
    """Point Canvas file/page hrefs and srcs at local copies. Leave YouTube/Piazza/etc."""
    _harvest_file_ids(html, file_by_id, files_by_name)

    def replace(match: re.Match[str]) -> str:
        url = unescape(match.group("url")).strip()
        if not url or _SKIP_URL.search(url):
            return match.group(0)
        local = _local_target(
            url,
            html,
            match.start(),
            file_by_id=file_by_id,
            page_by_slug=page_by_slug,
            files_by_name=files_by_name,
        )
        if local is None or not local.exists():
            return match.group(0)
        href = local_href(html_path, local)
        return f'{match.group("pre")}{match.group("q")}{href}{match.group("q")}'

    return _ATTR_URL.sub(replace, html)


def _harvest_file_ids(
    html: str,
    file_by_id: dict[int, Path],
    files_by_name: dict[str, list[Path]],
) -> None:
    """Fill file IDs from title/alt/link text so a second href to the same file can resolve."""
    for match in _ATTR_URL.finditer(html):
        url = unescape(match.group("url")).strip()
        file_id = _file_id_from_url(url)
        if file_id is None or file_id in file_by_id:
            continue
        guessed = _guess_file(html, match.start(), files_by_name)
        if guessed is not None:
            file_by_id[file_id] = guessed


def rewrite_course_html(
    root: Path,
    extra_files: dict[int, Path] | None = None,
    extra_pages: dict[str, Path] | None = None,
) -> int:
    """Rewrite every HTML file in a course folder. Returns how many files changed."""
    root = Path(root)
    file_by_id = _load_file_index(root)
    if extra_files:
        file_by_id.update({int(k): Path(v) for k, v in extra_files.items()})
    page_by_slug: dict[str, Path] = dict(extra_pages or {})
    files_by_name: dict[str, list[Path]] = defaultdict(list)
    html_files: list[Path] = []

    for path in iter_files(root):
        if path.name.lower() in _INDEX_SKIP:
            continue
        if path.suffix.lower() == ".html":
            html_files.append(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            match = _SLUG_META.search(text)
            if match:
                page_by_slug.setdefault(unquote(match.group(1).strip()), path)
            continue
        files_by_name[path.name.lower()].append(path)

    blobs: list[tuple[Path, str]] = []
    for path in html_files:
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue
        blobs.append((path, original))
        _harvest_file_ids(original, file_by_id, files_by_name)

    changed = 0
    for path, original in blobs:
        updated = rewrite_local_links(
            original,
            path,
            file_by_id=file_by_id,
            page_by_slug=page_by_slug,
            files_by_name=files_by_name,
        )
        if updated == original:
            continue
        try:
            path.write_text(updated, encoding="utf-8")
            changed += 1
        except OSError:
            continue
    _save_file_index(root, file_by_id)
    return changed


def rewrite_library(download_dir: Path) -> dict[str, int]:
    """Rewrite HTML across every archived course. Returns course folder -> files changed."""
    results: dict[str, int] = {}
    root = Path(download_dir)
    for manifest in iter_files(root):
        if manifest.name != "_manifest.json":
            continue
        course = manifest.parent
        changed = rewrite_course_html(course)
        results[str(course.relative_to(root))] = changed
    return results


def _load_file_index(root: Path) -> dict[int, Path]:
    path = root / "_file_index.json"
    mapping: dict[int, Path] = {}
    if not path.exists():
        return mapping
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return mapping
    if not isinstance(raw, dict):
        return mapping
    for key, rel in raw.items():
        try:
            dest = root / str(rel)
        except TypeError:
            continue
        if dest.exists():
            mapping[int(key)] = dest
    return mapping


def _save_file_index(root: Path, file_by_id: dict[int, Path]) -> None:
    payload: dict[str, str] = {}
    root_abs = root.resolve()
    for file_id, dest in sorted(file_by_id.items(), key=lambda item: item[0]):
        try:
            rel = Path(os.path.abspath(str(dest))).resolve().relative_to(root_abs)
        except ValueError:
            continue
        payload[str(file_id)] = rel.as_posix()
    if not payload:
        return
    (root / "_file_index.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _local_target(
    url: str,
    html: str,
    pos: int,
    *,
    file_by_id: dict[int, Path],
    page_by_slug: dict[str, Path],
    files_by_name: dict[str, list[Path]],
) -> Path | None:
    if not _is_canvas_file_or_page(url):
        return None
    file_id = _file_id_from_url(url)
    if file_id is not None:
        known = file_by_id.get(file_id)
        if known is not None:
            return known
        guessed = _guess_file(html, pos, files_by_name)
        if guessed is not None:
            file_by_id.setdefault(file_id, guessed)
            return guessed
        return None
    slug = _page_slug_from_url(url)
    if slug:
        return page_by_slug.get(slug)
    return None


def _is_canvas_file_or_page(url: str) -> bool:
    if _SKIP_URL.search(url):
        return False
    if not _CANVAS_FILE_OR_PAGE.search(url):
        return False
    if re.match(r"^https?://", url, re.I):
        host = (urlparse(url).netloc or "").lower()
        if host and not any(token in host for token in ("utoronto", "instructure", "canvas")):
            return False
    return True


def _file_id_from_url(url: str) -> int | None:
    match = _FILE_ID_IN_URL.search(url)
    return int(match.group(1)) if match else None


def _page_slug_from_url(url: str) -> str:
    match = _PAGE_SLUG_IN_URL.search(url)
    if not match:
        return ""
    return unquote(match.group(1)).strip().strip("/")


def _guess_file(html: str, pos: int, files_by_name: dict[str, list[Path]]) -> Path | None:
    tag = _tag_around(html, pos)
    for raw in _TITLE_ATTR.findall(tag):
        found = _lookup_name(unescape(raw), files_by_name)
        if found is not None:
            return found
    text = _anchor_text(html, html.find(">", pos) + 1 if html.find(">", pos) >= 0 else pos)
    if not text:
        return None
    found = _lookup_name(text, files_by_name)
    if found is not None:
        return found
    stem = safe_name(text).lower()
    stem_hits: list[Path] = []
    for name, paths in files_by_name.items():
        if Path(name).stem.lower() == stem:
            stem_hits.extend(paths)
    return _pick_unique(stem_hits)


def _lookup_name(name: str, files_by_name: dict[str, list[Path]]) -> Path | None:
    key = Path(safe_name(name)).name.lower()
    hits = files_by_name.get(key) or files_by_name.get(name.lower())
    picked = _pick_unique(hits)
    if picked is not None:
        return picked
    wanted = Path(key)
    stem, suffix = wanted.stem, wanted.suffix.lower()
    if len(stem) < 8:
        return None
    clipped: list[Path] = []
    for other_key, paths in files_by_name.items():
        other = Path(other_key)
        if other.suffix.lower() != suffix:
            continue
        if stem.startswith(other.stem) and 4 <= len(other.stem) <= 8 < len(stem):
            clipped.extend(paths)
    return _pick_unique(clipped)


def _pick_unique(paths: list[Path] | None) -> Path | None:
    if not paths:
        return None
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    if len(existing) == 1:
        return existing[0]
    in_files = [path for path in existing if "Files" in path.parts]
    if len(in_files) == 1:
        return in_files[0]
    return (in_files or existing)[0]


def _tag_around(html: str, pos: int) -> str:
    start = html.rfind("<", 0, pos + 1)
    end = html.find(">", pos)
    if start < 0 or end < 0:
        return ""
    return html[start : end + 1]


def _anchor_text(html: str, tag_end: int) -> str:
    if tag_end <= 0:
        return ""
    close = html.lower().find("</a>", tag_end, tag_end + 240)
    if close < 0:
        return ""
    inner = re.sub(r"<[^>]+>", "", html[tag_end:close])
    return unescape(inner).strip()
