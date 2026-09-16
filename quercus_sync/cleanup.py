from __future__ import annotations

import shutil
from pathlib import Path

from quercus_sync.paths import iter_files, long_path


def truncated_course_groups(term_dir: Path) -> list[list[Path]]:
    """Course folders in one term where a short name is a prefix of a longer sibling."""
    courses = sorted(
        (path for path in term_dir.iterdir() if path.is_dir()),
        key=lambda path: (-len(path.name), path.name),
    )
    used: set[Path] = set()
    groups: list[list[Path]] = []
    for canonical in courses:
        if canonical in used:
            continue
        stubs = [
            other
            for other in courses
            if other != canonical
            and len(other.name) >= 24
            and canonical.name.startswith(other.name)
        ]
        if not stubs:
            continue
        used.add(canonical)
        used.update(stubs)
        groups.append([canonical, *stubs])
    return groups


def merge_truncated_folders(download_dir: Path) -> list[dict[str, object]]:
    """Copy unique files into the full course folder, then delete cutoff siblings."""
    root = Path(download_dir)
    report: list[dict[str, object]] = []
    if not root.exists():
        return report
    for term in sorted(path for path in root.iterdir() if path.is_dir()):
        for group in truncated_course_groups(term):
            canonical, *stubs = group
            copied = 0
            skipped = 0
            deleted: list[str] = []
            failed: list[str] = []
            for stub in stubs:
                added, already = _merge_tree(stub, canonical)
                copied += added
                skipped += already
                try:
                    shutil.rmtree(long_path(stub))
                    deleted.append(stub.name)
                except OSError as exc:
                    failed.append(f"{stub.name}: {exc}")
            report.append(
                {
                    "term": term.name,
                    "keep": canonical.name,
                    "copied": copied,
                    "already": skipped,
                    "deleted": deleted,
                    "failed": failed,
                }
            )
    return report


def _merge_tree(source: Path, dest_root: Path) -> tuple[int, int]:
    copied = 0
    skipped = 0
    src = long_path(source)
    dest_base = long_path(dest_root)
    for path in iter_files(source):
        long_file = long_path(path)
        rel = long_file.relative_to(src)
        dest = dest_base / rel
        if dest.exists():
            skipped += 1
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(long_file, dest)
            copied += 1
        except OSError:
            # MAX_PATH or OneDrive lock: leave the stub so the file is not lost.
            skipped += 1
    return copied, skipped
