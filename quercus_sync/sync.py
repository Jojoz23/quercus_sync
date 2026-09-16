from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from quercus_sync.htmlutil import (
    canvas_file_ids,
    canvas_page_slugs,
    html_document,
    html_external_links,
    html_without_urls,
    iso,
    rewrite_course_html,
)
from quercus_sync.paths import clip_path, course_folder, safe_name, unique_path

EventCallback = Callable[[dict[str, Any]], None]


class SyncStopped(RuntimeError):
    """Raised when the user asks the archive to stop."""


class SupportsCanvas(Protocol):
    def me(self) -> dict[str, Any]: ...
    def courses(self) -> list[dict[str, Any]]: ...
    def files(self, course_id: int) -> list[dict[str, Any]]: ...
    def file(self, file_id: int) -> dict[str, Any]: ...
    def folder_files(self, folder_id: int) -> list[dict[str, Any]]: ...
    def folders(self, course_id: int) -> list[dict[str, Any]]: ...
    def front_page(self, course_id: int) -> dict[str, Any] | None: ...
    def modules(self, course_id: int) -> list[dict[str, Any]]: ...
    def pages(self, course_id: int) -> list[dict[str, Any]]: ...
    def page(self, course_id: int, slug: str) -> dict[str, Any] | None: ...
    def assignments(self, course_id: int) -> list[dict[str, Any]]: ...
    def announcements(self, course_id: int) -> list[dict[str, Any]]: ...
    def discussions(self, course_id: int) -> list[dict[str, Any]]: ...
    def discussion(self, course_id: int, topic_id: int) -> dict[str, Any]: ...
    def quizzes(self, course_id: int) -> list[dict[str, Any]]: ...
    def calendar_events(self, course_id: int) -> list[dict[str, Any]]: ...
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
    "discussions",
    "quizzes",
    "calendar",
)

def download_workers() -> int:
    """Parallel file downloads. JSON listing stays sequential to limit 429s."""
    raw = os.environ.get("QUERCUS_DOWNLOAD_WORKERS", "20")
    try:
        return max(1, min(int(raw), 32))
    except ValueError:
        return 20


class CourseSync:
    def __init__(
        self,
        client: SupportsCanvas,
        download_dir: Path,
        include: list[str] | None = None,
        on_event: EventCallback | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.client = client
        self.download_dir = Path(download_dir)
        self.include = set(include or DEFAULT_INCLUDE)
        self.on_event = on_event or (lambda _event: None)
        self.stats = SyncStats()
        self.errors: list[str] = []
        self._lock = threading.Lock()
        self._stop = stop_event or threading.Event()
        self._course_root: Path | None = None
        self._seen_page_slugs: set[str] = set()
        self._course_links: list[dict[str, str]] = []
        self._file_paths: dict[int, Path] = {}
        self._page_paths: dict[str, Path] = {}

    def request_stop(self) -> None:
        self._stop.set()

    def _stopped(self) -> bool:
        return self._stop.is_set()

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise SyncStopped("Stopped")

    def emit(self, **event: Any) -> None:
        self.on_event(event)

    def list_courses(self) -> list[dict[str, Any]]:
        courses = [c for c in self.client.courses() if is_accessible_course(c)]
        unique: list[dict[str, Any]] = []
        seen: set[Any] = set()
        for course in courses:
            course_id = course.get("id")
            if course_id in seen:
                continue
            seen.add(course_id)
            unique.append(course)
        unique.sort(
            key=lambda c: (
                0 if course_access(c) == "current" else 1,
                (c.get("term") or {}).get("name") or "",
                c.get("course_code") or c.get("name") or "",
            )
        )
        return unique

    def run(self, course_ids: list[int] | None = None) -> SyncResult:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        courses = self.list_courses()
        if course_ids:
            wanted = set(course_ids)
            courses = [c for c in courses if int(c["id"]) in wanted]
        self.emit(type="log", message=f"Archiving {len(courses)} course(s) into {self.download_dir}")
        for course in courses:
            try:
                self._check_stop()
                self._sync_course(course)
                self.stats.courses += 1
            except SyncStopped:
                self.emit(type="log", message="Stopped")
                break
            except Exception as exc:  # noqa: BLE001 — surface per-course failures
                message = f"{course.get('course_code')}: {exc}"
                self.errors.append(message)
                self.emit(type="error", message=message)
        self.emit(type="done", stats=self.stats.as_dict(), errors=self.errors)
        return SyncResult(stats=self.stats, errors=self.errors, root=str(self.download_dir))

    def _sync_course(self, course: dict[str, Any]) -> None:
        term = safe_name((course.get("term") or {}).get("name") or "No term")
        folder_name = course_folder(course.get("course_code") or "", course.get("name") or "Untitled")
        root = clip_path(self.download_dir / term / folder_name)
        root.mkdir(parents=True, exist_ok=True)
        self._course_root = root
        self._seen_page_slugs = set()
        self._course_links = []
        self._file_paths = {}
        self._page_paths = {}
        self.emit(
            type="course_start",
            course=root.name,
            term=term,
            id=course["id"],
        )
        course_id = int(course["id"])
        folders: dict[int, dict[str, Any]] = {}
        if "files" in self.include:
            try:
                folders = {f["id"]: f for f in self.client.folders(course_id) if f.get("id") is not None}
            except Exception as exc:  # noqa: BLE001
                self._skip("folders", str(exc))
        html_blobs: list[str] = []
        known_ids: set[Any] = set()
        module_slugs: set[str] = set()

        if "syllabus" in self.include:
            body = course.get("syllabus_body") or ""
            html_blobs.append(body)
            self._collect_html_links("Syllabus", body)
            self._write_html(
                root / "Syllabus.html",
                f"{folder_name} syllabus",
                body,
                {"Term": term, "Course": course.get("course_code")},
            )

        if "files" in self.include:
            self._check_stop()
            known_ids = self._sync_files(course_id, root, folders)

        if "modules" in self.include:
            self._check_stop()
            module_slugs = self._sync_modules(course_id, root)

        if "pages" in self.include:
            self._check_stop()
            html_blobs.extend(self._sync_pages(course_id, root, extra_slugs=module_slugs))

        if "assignments" in self.include:
            self._check_stop()
            html_blobs.extend(self._sync_assignments(course_id, root))

        if "announcements" in self.include:
            self._check_stop()
            html_blobs.extend(self._sync_announcements(course_id, root))

        if "discussions" in self.include:
            self._check_stop()
            html_blobs.extend(self._sync_discussions(course_id, root))

        if "quizzes" in self.include:
            self._check_stop()
            html_blobs.extend(self._sync_quizzes(course_id, root))

        if "calendar" in self.include:
            self._check_stop()
            self._sync_calendar(course_id, root)

        if "pages" in self.include:
            extra_slugs: set[str] = set()
            for blob in html_blobs:
                extra_slugs.update(canvas_page_slugs(blob))
            if extra_slugs - self._seen_page_slugs:
                self._check_stop()
                html_blobs.extend(self._sync_pages(course_id, root, extra_slugs=extra_slugs))

        if "files" in self.include:
            self._check_stop()
            self._sync_html_files(course_id, root, known_ids, html_blobs)

        rewritten = rewrite_course_html(root, extra_files=self._file_paths, extra_pages=self._page_paths)
        if rewritten:
            self.emit(type="log", message=f"Pointed {rewritten} HTML file(s) at local copies")

        self._write_links(root)

        manifest = {
            "course_id": course_id,
            "name": course.get("name"),
            "course_code": course.get("course_code"),
            "term": term,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "include": sorted(self.include),
        }
        (root / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.emit(type="course_done", course=root.name)

    def _sync_files(self, course_id: int, root: Path, folders: dict[int, dict[str, Any]]) -> set[Any]:
        try:
            catalog = list(self.client.files(course_id))
        except Exception as exc:  # noqa: BLE001
            self._skip("Files tab", str(exc))
            catalog = []
        known = {item.get("id") for item in catalog if item.get("id") is not None}
        for folder in folders.values():
            folder_id = folder.get("id")
            if folder_id is None:
                continue
            try:
                extra_rows = self.client.folder_files(int(folder_id))
            except Exception as exc:  # noqa: BLE001
                self._fail(f"folder {folder.get('full_name') or folder_id}", str(exc))
                continue
            for item in extra_rows:
                item_id = item.get("id")
                if item_id in known:
                    continue
                catalog.append(item)
                if item_id is not None:
                    known.add(item_id)
        catalog.extend(self._extra_files(course_id, known))
        seen: set[int] = set()
        jobs: list[dict[str, Any]] = []
        for item in catalog:
            file_id = item.get("id")
            if file_id in seen:
                continue
            if file_id is not None:
                seen.add(int(file_id))
                known.add(int(file_id))
            jobs.append(item)
        self._run_parallel(lambda row: self._save_file_item(row, root, folders), jobs)
        return known

    def _run_parallel(self, fn: Callable[[Any], None], items: list[Any]) -> None:
        if not items:
            return
        if len(items) == 1:
            fn(items[0])
            return
        workers = min(download_workers(), len(items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for item in items:
                if self._stopped():
                    break
                futures.append(pool.submit(fn, item))
            for future in as_completed(futures):
                if self._stopped():
                    for pending in futures:
                        pending.cancel()
                    break
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    self._fail("download", str(exc))

    def _save_file_item(
        self,
        item: dict[str, Any],
        root: Path,
        folders: dict[int, dict[str, Any]],
    ) -> None:
        if self._stopped():
            return
        if item.get("locked_for_user"):
            self._skip(item.get("display_name") or "file", "locked on Quercus")
            return
        folder_meta = folders.get(item.get("folder_id")) or {}
        relative = _folder_relative(
            folder_meta.get("full_name") or item.get("_folder") or "course files"
        )
        dest_dir = root / "Files" / relative
        filename = safe_name(item.get("display_name") or item.get("filename") or f"file-{item.get('id')}")
        dest = clip_path(dest_dir / filename, keep_prefix=root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = self._download_file(item.get("url"), dest, label=filename, size=item.get("size"))
        file_id = item.get("id")
        recorded = written if written is not None else (dest if dest.exists() else None)
        if file_id is not None and recorded is not None:
            with self._lock:
                self._file_paths[int(file_id)] = recorded

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
        try:
            posts = self.client.announcements(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("announcements", str(exc))
            posts = []
        for post in posts:
            extras.extend(
                self._collect_attachments(
                    post.get("attachments") or [],
                    known_ids,
                    f"course files/From announcements/{post.get('title') or 'announcement'}",
                )
            )
        try:
            topics = self.client.discussions(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("discussions", str(exc))
            topics = []
        for topic in topics:
            extras.extend(
                self._collect_attachments(
                    topic.get("attachments") or [],
                    known_ids,
                    f"course files/From discussions/{topic.get('title') or 'discussion'}",
                )
            )
        return extras

    def _collect_attachments(
        self,
        attachments: list[dict[str, Any]],
        known_ids: set[Any],
        folder: str,
    ) -> list[dict[str, Any]]:
        extras: list[dict[str, Any]] = []
        for attachment in attachments:
            att_id = attachment.get("id")
            if att_id in known_ids:
                continue
            attachment.setdefault("_folder", folder)
            extras.append(attachment)
            if att_id is not None:
                known_ids.add(att_id)
        return extras

    def _sync_html_files(
        self,
        course_id: int,
        root: Path,
        known_ids: set[Any],
        html_blobs: list[str],
    ) -> None:
        """Download Canvas files linked in page/syllabus HTML even if hidden from Files."""
        wanted: set[int] = set()
        for blob in html_blobs:
            wanted.update(canvas_file_ids(blob))
        extras: list[dict[str, Any]] = []
        for file_id in sorted(wanted):
            if file_id in known_ids:
                continue
            try:
                meta = self.client.file(file_id)
            except Exception as exc:  # noqa: BLE001
                self._fail(f"linked file {file_id}", str(exc))
                continue
            meta.setdefault("_folder", "course files/From pages")
            known_ids.add(file_id)
            extras.append(meta)
        self._run_parallel(lambda row: self._save_file_item(row, root, {}), extras)

    def _sync_modules(self, course_id: int, root: Path) -> set[str]:
        modules = self.client.modules(course_id)
        index_rows = []
        page_slugs: set[str] = set()
        for module in modules:
            name = safe_name(module.get("name") or f"Module {module.get('id')}")
            position = module.get("position") or 0
            module_dir = clip_path(root / "Modules" / f"{int(position):02d} {name}", keep_prefix=root)
            module_dir.mkdir(parents=True, exist_ok=True)
            lines = [f"# {module.get('name')}", ""]
            source = f"Modules / {module.get('name')}"
            for item in module.get("items") or []:
                title = item.get("title") or item.get("type")
                kind = item.get("type")
                lines.append(f"- {kind}: {title}")
                if kind in {"Page", "WikiPage"}:
                    slug = item.get("page_url")
                    if slug:
                        page_slugs.add(str(slug))
                    page_slugs.update(canvas_page_slugs(item.get("html_url") or ""))
                url = item.get("external_url") or item.get("url")
                if kind in {"ExternalUrl", "ExternalTool"} and url:
                    self._add_link(source, url, str(title or url))
                    link_path = clip_path(module_dir / f"{safe_name(title)}.url.txt", keep_prefix=root)
                    try:
                        link_path.parent.mkdir(parents=True, exist_ok=True)
                        link_path.write_text(url + "\n", encoding="utf-8")
                        self._saved(link_path)
                    except OSError as exc:
                        self._fail(title, str(exc))
            try:
                module_md = clip_path(module_dir / "module.md", keep_prefix=root)
                module_md.parent.mkdir(parents=True, exist_ok=True)
                module_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self._saved(module_md)
            except OSError as exc:
                self._fail(name, str(exc))
            index_rows.append(f"- {position}. {module.get('name')}")
        if index_rows:
            readme = clip_path(root / "Modules" / "README.md", keep_prefix=root)
            readme.parent.mkdir(parents=True, exist_ok=True)
            readme.write_text("# Modules\n\n" + "\n".join(index_rows) + "\n", encoding="utf-8")
            self._saved(readme)
        return page_slugs

    def _sync_pages(self, course_id: int, root: Path, extra_slugs: set[str] | None = None) -> list[str]:
        dest = clip_path(root / "Pages", keep_prefix=root)
        dest.mkdir(parents=True, exist_ok=True)
        bodies: list[str] = []
        queue: list[str] = []
        by_slug: dict[str, dict[str, Any]] = {}

        def enqueue(slug: str | None) -> None:
            if not slug:
                return
            text = str(slug).strip().strip("/")
            if not text or text in self._seen_page_slugs:
                return
            self._seen_page_slugs.add(text)
            queue.append(text)

        summaries = list(self.client.pages(course_id))
        try:
            front = self.client.front_page(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("front page", str(exc))
            front = None
        if front and front.get("url"):
            by_slug[str(front["url"])] = front
            enqueue(front.get("url"))
        for summary in summaries:
            slug = summary.get("url")
            if slug:
                by_slug.setdefault(str(slug), summary)
                enqueue(slug)
        for slug in extra_slugs or ():
            enqueue(slug)

        while queue:
            slug = queue.pop(0)
            summary = by_slug.get(slug) or {}
            try:
                page = summary if "body" in summary else self.client.page(course_id, slug)
            except Exception as exc:  # noqa: BLE001
                self._fail(slug, str(exc))
                continue
            if not page:
                self._skip(slug, "page not available")
                continue
            body = page.get("body") or ""
            bodies.append(body)
            title = page.get("title") or slug
            filename = safe_name(title) + ".html"
            html_path = dest / filename
            self._write_html(
                html_path,
                title,
                body,
                {"Updated": iso(page.get("updated_at")), "Slug": slug},
            )
            self._page_paths[slug] = clip_path(html_path, keep_prefix=self._course_root)
            self._collect_html_links(f"Pages / {title}", body)
            for linked in canvas_page_slugs(body):
                enqueue(linked)
        return bodies

    def _sync_assignments(self, course_id: int, root: Path) -> list[str]:
        dest = root / "Assignments"
        dest.mkdir(parents=True, exist_ok=True)
        bodies: list[str] = []
        for assignment in self.client.assignments(course_id):
            name = safe_name(assignment.get("name") or f"assignment-{assignment.get('id')}")
            body = assignment.get("description") or ""
            bodies.append(body)
            self._collect_html_links(f"Assignments / {assignment.get('name') or name}", body)
            path = dest / f"{name}.html"
            self._write_html(
                path,
                assignment.get("name") or name,
                body,
                {
                    "Due": iso(assignment.get("due_at")) or "No due date",
                    "Points": assignment.get("points_possible"),
                },
            )
        return bodies

    def _sync_announcements(self, course_id: int, root: Path) -> list[str]:
        dest = root / "Announcements"
        dest.mkdir(parents=True, exist_ok=True)
        bodies: list[str] = []
        for post in self.client.announcements(course_id):
            posted = (post.get("posted_at") or "")[:10]
            name = safe_name(f"{posted} {post.get('title') or post.get('id')}") + ".html"
            body = post.get("message") or ""
            bodies.append(body)
            self._collect_html_links(f"Announcements / {post.get('title') or 'Announcement'}", body)
            self._write_html(
                dest / name,
                post.get("title") or "Announcement",
                body,
                {"Posted": iso(post.get("posted_at"))},
            )
        return bodies

    def _sync_discussions(self, course_id: int, root: Path) -> list[str]:
        dest = root / "Discussions"
        dest.mkdir(parents=True, exist_ok=True)
        bodies: list[str] = []
        for topic in self.client.discussions(course_id):
            title = topic.get("title") or f"topic-{topic.get('id')}"
            body = topic.get("message") or ""
            bodies.append(body)
            self._collect_html_links(f"Discussions / {title}", body)
            try:
                view = self.client.discussion(course_id, int(topic["id"]))
            except Exception:
                view = {"view": []}
            replies = []
            for reply in view.get("view") or []:
                bodies.append(reply.get("message") or "")
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
        return bodies

    def _sync_quizzes(self, course_id: int, root: Path) -> list[str]:
        """Quiz titles and instructions only — not question banks."""
        dest = root / "Quizzes"
        dest.mkdir(parents=True, exist_ok=True)
        bodies: list[str] = []
        try:
            quizzes = self.client.quizzes(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("quizzes", str(exc))
            return bodies
        if not quizzes:
            return bodies
        for quiz in quizzes:
            title = quiz.get("title") or f"quiz-{quiz.get('id')}"
            body = quiz.get("description") or ""
            bodies.append(body)
            self._collect_html_links(f"Quizzes / {title}", body)
            self._write_html(
                dest / (safe_name(title) + ".html"),
                title,
                body,
                {
                    "Due": iso(quiz.get("due_at")) or "No due date",
                    "Points": quiz.get("points_possible"),
                },
            )
        return bodies

    def _sync_calendar(self, course_id: int, root: Path) -> None:
        try:
            events = self.client.calendar_events(course_id)
        except Exception as exc:  # noqa: BLE001
            self._fail("calendar", str(exc))
            return
        if not events:
            return
        rows = []
        for event in events:
            title = event.get("title") or "Event"
            start = iso(event.get("start_at")) or iso(event.get("start_date"))
            desc = event.get("description") or ""
            rows.append(f"<h2>{title}</h2><p class='meta'>{start}</p>{desc}")
        self._write_html(
            root / "Calendar.html",
            "Course calendar",
            "\n".join(rows),
            {"Events": len(events)},
        )

    def _write_html(self, path: Path, title: str, body: str, meta: dict[str, Any] | None = None) -> None:
        path = clip_path(path, keep_prefix=self._course_root)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            document = html_document(title, body, meta)
            if path.exists():
                existing = path.read_text(encoding="utf-8")
                if existing == document or html_without_urls(existing) == html_without_urls(document):
                    self._skip(_rel(path, self.download_dir), "unchanged")
                    return
            path.write_text(document, encoding="utf-8")
            self._saved(path)
        except OSError as exc:
            self._fail(title, str(exc))

    def _download_file(self, url: str | None, dest: Path, label: str, size: int | None = None) -> Path | None:
        if self._stopped():
            return None
        if not url:
            self._skip(label, "no download URL")
            return dest if dest.exists() else None
        dest = clip_path(dest, keep_prefix=self._course_root)
        if dest.exists() and size and dest.stat().st_size == size:
            self._skip(_rel(dest, self.download_dir), "unchanged")
            return dest
        if dest.exists() and not size:
            self._skip(_rel(dest, self.download_dir), "already on disk")
            return dest
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                body, _content_type = self.client.download(url)
                dest.parent.mkdir(parents=True, exist_ok=True)
                target = dest if not dest.exists() else unique_path(dest)
                target.write_bytes(body)
                self._saved(target)
                return target
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                message = str(exc)
                retryable = any(
                    token in message
                    for token in ("10054", "10053", "Connection", "reset", "timed out", "Timeout")
                )
                if (not retryable) or attempt == 3:
                    break
                time.sleep(min(1.5 * (attempt + 1), 8))
        self._fail(label, str(last_error) if last_error else "download failed")
        return dest if dest.exists() else None

    def _saved(self, path: Path) -> None:
        rel = _rel(path, self.download_dir)
        with self._lock:
            self.stats.downloaded += 1
            self.emit(type="item", status="downloaded", path=rel, kind=_kind_from_path(rel))

    def _skip(self, label: str, reason: str) -> None:
        with self._lock:
            self.stats.skipped += 1
            self.emit(type="item", status="skipped", path=label, reason=reason)

    def _fail(self, label: str, reason: str) -> None:
        with self._lock:
            self.stats.failed += 1
            self.errors.append(f"{label}: {reason}")
            self.emit(type="item", status="failed", path=label, reason=reason)

    def _add_link(self, source: str, url: str, title: str = "") -> None:
        text = (url or "").strip()
        if not text:
            return
        self._course_links.append({"source": source, "url": text, "title": title or text})

    def _collect_html_links(self, source: str, html: str | None) -> None:
        for url, host in html_external_links(html):
            self._add_link(source, url, host)

    def _write_links(self, root: Path) -> None:
        if not self._course_links:
            return
        seen: set[str] = set()
        grouped: dict[str, list[dict[str, str]]] = {}
        for item in self._course_links:
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            grouped.setdefault(item["source"], []).append(item)
        lines = [
            "# Links",
            "",
            "External URLs from pages, modules, and announcements.",
            "YouTube, Zoom, Play, Piazza, and similar recordings stay on those sites — this file lists them.",
            "",
        ]
        for source, items in grouped.items():
            lines.append(f"## {source}")
            lines.append("")
            for item in items:
                title = item.get("title") or item["url"]
                lines.append(f"- [{title}]({item['url']})")
            lines.append("")
        path = clip_path(root / "Links.md", keep_prefix=root)
        try:
            path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            self._saved(path)
        except OSError as exc:
            self._fail("Links.md", str(exc))


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
    rel = rel.replace("\\", "/")
    if rel.endswith("Links.md"):
        return "links"
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
    if "/Quizzes/" in rel:
        return "quiz"
    if "/Discussions/" in rel:
        return "discussion"
    if rel.endswith("Calendar.html"):
        return "calendar"
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
