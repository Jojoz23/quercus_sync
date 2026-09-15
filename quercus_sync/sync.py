from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from quercus_sync.htmlutil import html_document, iso
from quercus_sync.paths import course_folder, safe_name, unique_path

EventCallback = Callable[[dict[str, Any]], None]


class SupportsCanvas(Protocol):
    def me(self) -> dict[str, Any]: ...
    def courses(self) -> list[dict[str, Any]]: ...
    def files(self, course_id: int) -> list[dict[str, Any]]: ...
    def file(self, file_id: int) -> dict[str, Any]: ...
    def folders(self, course_id: int) -> list[dict[str, Any]]: ...
    def modules(self, course_id: int) -> list[dict[str, Any]]: ...
    def pages(self, course_id: int) -> list[dict[str, Any]]: ...
    def page(self, course_id: int, slug: str) -> dict[str, Any]: ...
    def assignments(self, course_id: int) -> list[dict[str, Any]]: ...
    def announcements(self, course_id: int) -> list[dict[str, Any]]: ...
    def discussions(self, course_id: int) -> list[dict[str, Any]]: ...
    def discussion(self, course_id: int, topic_id: int) -> dict[str, Any]: ...
    def download(self, url: str) -> tuple[bytes, str]: ...


@dataclass
class SyncStats:
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    courses: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "courses": self.courses,
        }


@dataclass
class SyncResult:
    stats: SyncStats = field(default_factory=SyncStats)
    errors: list[str] = field(default_factory=list)
    root: str = ""


DEFAULT_INCLUDE = (
    "files",
    "modules",
    "pages",
    "assignments",
    "announcements",
    "syllabus",
)


class CourseSync:
    def __init__(
        self,
        client: SupportsCanvas,
        download_dir: Path,
        include: list[str] | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.client = client
        self.download_dir = Path(download_dir)
        self.include = set(include or DEFAULT_INCLUDE)
        self.on_event = on_event or (lambda _event: None)
        self.stats = SyncStats()
        self.errors: list[str] = []

    def emit(self, **event: Any) -> None:
        self.on_event(event)

    def list_courses(self) -> list[dict[str, Any]]:
        courses = [c for c in self.client.courses() if is_accessible_course(c)]
        courses.sort(
            key=lambda c: (
                0 if course_access(c) == "current" else 1,
                (c.get("term") or {}).get("name") or "",
                c.get("course_code") or c.get("name") or "",
            )
        )
        return courses

    def run(self, course_ids: list[int] | None = None) -> SyncResult:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        courses = self.list_courses()
        if course_ids:
            wanted = set(course_ids)
            courses = [c for c in courses if int(c["id"]) in wanted]
        self.emit(type="log", message=f"Archiving {len(courses)} course(s) into {self.download_dir}")
        for course in courses:
            try:
                self._sync_course(course)
                self.stats.courses += 1
            except Exception as exc:  # noqa: BLE001 — surface per-course failures
                message = f"{course.get('course_code')}: {exc}"
                self.errors.append(message)
                self.emit(type="error", message=message)
        self.emit(type="done", stats=self.stats.as_dict(), errors=self.errors)
        return SyncResult(stats=self.stats, errors=self.errors, root=str(self.download_dir))

    def _sync_course(self, course: dict[str, Any]) -> None:
        term = safe_name((course.get("term") or {}).get("name") or "No term")
        folder_name = course_folder(course.get("course_code") or "", course.get("name") or "Untitled")
        root = self.download_dir / term / folder_name
        root.mkdir(parents=True, exist_ok=True)
        self.emit(
            type="course_start",
            course=folder_name,
            term=term,
            id=course["id"],
        )
        course_id = int(course["id"])
        folders = {f["id"]: f for f in self.client.folders(course_id)} if "files" in self.include else {}

        if "syllabus" in self.include:
            self._write_html(
                root / "Syllabus.html",
                f"{folder_name} syllabus",
                course.get("syllabus_body") or "",
                {"Term": term, "Course": course.get("course_code")},
            )

        if "files" in self.include:
            self._sync_files(course_id, root, folders)

        if "modules" in self.include:
            self._sync_modules(course_id, root)

        if "pages" in self.include:
            self._sync_pages(course_id, root)

        if "assignments" in self.include:
            self._sync_assignments(course_id, root)

        if "announcements" in self.include:
            self._sync_announcements(course_id, root)

        if "discussions" in self.include:
            self._sync_discussions(course_id, root)

        manifest = {
            "course_id": course_id,
            "name": course.get("name"),
            "course_code": course.get("course_code"),
            "term": term,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "include": sorted(self.include),
        }
        (root / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.emit(type="course_done", course=folder_name)

    def _sync_files(self, course_id: int, root: Path, folders: dict[int, dict[str, Any]]) -> None:
        catalog = list(self.client.files(course_id))
        known = {item.get("id") for item in catalog if item.get("id") is not None}
        catalog.extend(self._extra_files(course_id, known))
        seen: set[int] = set()
        for item in catalog:
            file_id = item.get("id")
            if file_id in seen:
                continue
            if file_id is not None:
                seen.add(int(file_id))
            if item.get("locked_for_user"):
                self._skip(item.get("display_name") or "file", "locked on Quercus")
                continue
            folder_meta = folders.get(item.get("folder_id")) or {}
            relative = _folder_relative(
                folder_meta.get("full_name") or item.get("_folder") or "course files"
            )
            dest_dir = root / "Files" / relative
            dest_dir.mkdir(parents=True, exist_ok=True)
            filename = safe_name(item.get("display_name") or item.get("filename") or f"file-{item.get('id')}")
            dest = dest_dir / filename
            self._download_file(item.get("url"), dest, label=filename, size=item.get("size"))

    def _extra_files(self, course_id: int, known_ids: set[Any]) -> list[dict[str, Any]]:
        """Files attached to modules/assignments but missing from the Files tab."""
        extras: list[dict[str, Any]] = []
        try:
            modules = self.client.modules(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("modules", str(exc))
            modules = []
        for module in modules:
            for item in module.get("items") or []:
                if item.get("type") != "File":
                    continue
                content_id = item.get("content_id")
                if content_id in known_ids:
                    continue
                try:
                    meta = self.client.file(int(content_id))
                except Exception as exc:  # noqa: BLE001
                    self._fail(item.get("title") or str(content_id), str(exc))
                    continue
                meta.setdefault("_folder", "course files/From modules")
                extras.append(meta)
                known_ids.add(content_id)
        try:
            assignments = self.client.assignments(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("assignments", str(exc))
            assignments = []
        for assignment in assignments:
            for attachment in assignment.get("attachments") or []:
                att_id = attachment.get("id")
                if att_id in known_ids:
                    continue
                attachment.setdefault(
                    "_folder",
                    f"course files/From assignments/{assignment.get('name') or 'assignment'}",
                )
                extras.append(attachment)
                if att_id is not None:
                    known_ids.add(att_id)
        return extras

    def _sync_modules(self, course_id: int, root: Path) -> None:
        modules = self.client.modules(course_id)
        index_rows = []
        for module in modules:
            name = safe_name(module.get("name") or f"Module {module.get('id')}")
            position = module.get("position") or 0
            module_dir = root / "Modules" / f"{int(position):02d} {name}"
            module_dir.mkdir(parents=True, exist_ok=True)
            lines = [f"# {module.get('name')}", ""]
            for item in module.get("items") or []:
                title = item.get("title") or item.get("type")
                kind = item.get("type")
                lines.append(f"- {kind}: {title}")
                if kind == "ExternalUrl" and item.get("external_url"):
                    (module_dir / f"{safe_name(title)}.url.txt").write_text(
                        item["external_url"] + "\n", encoding="utf-8"
                    )
                    self._saved(module_dir / f"{safe_name(title)}.url.txt")
            (module_dir / "module.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._saved(module_dir / "module.md")
            index_rows.append(f"- {position}. {module.get('name')}")
        if index_rows:
            (root / "Modules" / "README.md").write_text(
                "# Modules\n\n" + "\n".join(index_rows) + "\n", encoding="utf-8"
            )
            self._saved(root / "Modules" / "README.md")

    def _sync_pages(self, course_id: int, root: Path) -> None:
        dest = root / "Pages"
        dest.mkdir(parents=True, exist_ok=True)
        for summary in self.client.pages(course_id):
            slug = summary.get("url")
            if not slug:
                continue
            try:
                page = self.client.page(course_id, slug)
            except Exception as exc:  # noqa: BLE001
                self._fail(slug, str(exc))
                continue
            filename = safe_name(page.get("title") or slug) + ".html"
            self._write_html(
                dest / filename,
                page.get("title") or slug,
                page.get("body") or "",
                {"Updated": iso(page.get("updated_at")), "Slug": slug},
            )

    def _sync_assignments(self, course_id: int, root: Path) -> None:
        dest = root / "Assignments"
        dest.mkdir(parents=True, exist_ok=True)
        for assignment in self.client.assignments(course_id):
            name = safe_name(assignment.get("name") or f"assignment-{assignment.get('id')}")
            path = dest / f"{name}.html"
            self._write_html(
                path,
                assignment.get("name") or name,
                assignment.get("description") or "",
                {
                    "Due": iso(assignment.get("due_at")) or "No due date",
                    "Points": assignment.get("points_possible"),
                },
            )

    def _sync_announcements(self, course_id: int, root: Path) -> None:
        dest = root / "Announcements"
        dest.mkdir(parents=True, exist_ok=True)
        for post in self.client.announcements(course_id):
            posted = (post.get("posted_at") or "")[:10]
            name = safe_name(f"{posted} {post.get('title') or post.get('id')}") + ".html"
            self._write_html(
                dest / name,
                post.get("title") or "Announcement",
                post.get("message") or "",
                {"Posted": iso(post.get("posted_at"))},
            )

    def _sync_discussions(self, course_id: int, root: Path) -> None:
        dest = root / "Discussions"
        dest.mkdir(parents=True, exist_ok=True)
        for topic in self.client.discussions(course_id):
            title = topic.get("title") or f"topic-{topic.get('id')}"
            body = topic.get("message") or ""
            try:
                view = self.client.discussion(course_id, int(topic["id"]))
            except Exception:
                view = {"view": []}
            replies = []
            for reply in view.get("view") or []:
                replies.append(
                    f"<li>{reply.get('message') or ''}<p class='meta'>user {reply.get('user_id')} · {iso(reply.get('created_at'))}</p></li>"
                )
            extra = f"<h2>Thread</h2><ol>{''.join(replies)}</ol>" if replies else ""
            self._write_html(
                dest / (safe_name(title) + ".html"),
                title,
                (body or "") + extra,
                {"Posted": iso(topic.get("posted_at"))},
            )

    def _write_html(self, path: Path, title: str, body: str, meta: dict[str, Any] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = html_document(title, body, meta)
        if path.exists() and path.read_text(encoding="utf-8") == document:
            self._skip(str(path.relative_to(self.download_dir)), "unchanged")
            return
        path.write_text(document, encoding="utf-8")
        self._saved(path)

    def _download_file(self, url: str | None, dest: Path, label: str, size: int | None = None) -> None:
        if not url:
            self._skip(label, "no download URL")
            return
        if dest.exists() and size and dest.stat().st_size == size:
            self._skip(str(dest.relative_to(self.download_dir)), "unchanged")
            return
        if dest.exists() and not size:
            self._skip(str(dest.relative_to(self.download_dir)), "already on disk")
            return
        try:
            body, _content_type = self.client.download(url)
        except Exception as exc:  # noqa: BLE001
            self._fail(label, str(exc))
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = dest if not dest.exists() else unique_path(dest)
        target.write_bytes(body)
        self._saved(target)

    def _saved(self, path: Path) -> None:
        self.stats.downloaded += 1
        rel = _rel(path, self.download_dir)
        self.emit(type="item", status="downloaded", path=rel, kind=_kind_from_path(rel))

    def _skip(self, label: str, reason: str) -> None:
        self.stats.skipped += 1
        self.emit(type="item", status="skipped", path=label, reason=reason)

    def _fail(self, label: str, reason: str) -> None:
        self.stats.failed += 1
        self.errors.append(f"{label}: {reason}")
        self.emit(type="item", status="failed", path=label, reason=reason)


def _folder_relative(full_name: str) -> Path:
    text = full_name.replace("\\", "/")
    if text.lower().startswith("course files"):
        text = text[len("course files") :].lstrip("/")
    parts = [safe_name(part) for part in text.split("/") if part]
    return Path(*parts) if parts else Path(".")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _kind_from_path(rel: str) -> str:
    if "/Files/" in rel or rel.startswith("Files"):
        return "file"
    if "/Pages/" in rel:
        return "page"
    if "/Assignments/" in rel:
        return "assignment"
    if "/Announcements/" in rel:
        return "announcement"
    if "/Modules/" in rel:
        return "module"
    if rel.endswith("Syllabus.html"):
        return "syllabus"
    return "item"


def is_accessible_course(course: dict[str, Any]) -> bool:
    """True when this enrolment can still open the course (same rule as the website)."""
    if course.get("access_restricted_by_date"):
        return False
    if course.get("workflow_state") == "deleted":
        return False
    return bool(course.get("name"))


def course_access(course: dict[str, Any]) -> str:
    if course.get("concluded") or course.get("workflow_state") == "completed":
        return "past"
    states = {(row.get("enrollment_state") or "") for row in course.get("enrollments") or []}
    if states and "active" not in states and states & {"completed", "inactive"}:
        return "past"
    return "current"


def library_tree(download_dir: Path, limit: int = 400) -> list[dict[str, Any]]:
    root = Path(download_dir)
    if not root.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = str(path.relative_to(root))
        entries.append(
            {
                "path": rel,
                "name": path.name,
                "size": path.stat().st_size,
                "kind": _kind_from_path(rel),
            }
        )
        if len(entries) >= limit:
            break
    return entries
