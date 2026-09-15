from pathlib import Path

from quercus_sync.mock import MockCanvasClient
from quercus_sync.sync import CourseSync, library_tree


def test_mock_sync_writes_course_tree(tmp_path: Path):
    events = []
    engine = CourseSync(MockCanvasClient(), tmp_path, on_event=events.append)
    result = engine.run([148001])
    assert result.stats.courses == 1
    assert result.stats.downloaded > 8
    assert result.stats.failed == 0
    files = list(tmp_path.rglob("*"))
    names = {path.name for path in files if path.is_file()}
    assert "Syllabus.html" in names
    assert "Week 01 — Python recap.pdf" in names
    assert "Lab 2 — Recursion.html" in names
    assert "_manifest.json" in names
    kinds = {e.get("type") for e in events}
    assert "done" in kinds
    assert "course_start" in kinds


def test_second_sync_skips_unchanged_files(tmp_path: Path):
    engine = CourseSync(MockCanvasClient(), tmp_path)
    first = engine.run([148001])
    engine2 = CourseSync(MockCanvasClient(), tmp_path)
    second = engine2.run([148001])
    assert first.stats.downloaded > 0
    assert second.stats.skipped >= 3
    tree = library_tree(tmp_path)
    assert any(item["kind"] == "file" for item in tree)


def test_list_courses_has_utm_sample_set():
    courses = CourseSync(MockCanvasClient(), Path(".")).list_courses()
    codes = {c["course_code"] for c in courses}
    assert "CSC148H5 F" in codes
    assert "CSC108H5 S" in codes
    assert "HIS101H5 F" not in codes
    assert len(courses) == 5


def test_past_term_pulls_module_and_assignment_files(tmp_path: Path):
    result = CourseSync(MockCanvasClient(), tmp_path).run([108001])
    assert result.stats.failed == 0
    names = {path.name for path in tmp_path.rglob("*") if path.is_file()}
    assert "Week 08 lists.pdf" in names
    assert "Review session handout.pdf" in names
    assert "lab9-starter.zip" in names


def test_extracts_canvas_file_ids_from_page_html():
    from quercus_sync.htmlutil import canvas_file_ids

    html = '<a href="https://q.utoronto.ca/courses/1/files/77/download?download_frd=1">note</a>'
    assert canvas_file_ids(html) == {77}
    assert canvas_file_ids("") == set()


def test_page_linked_file_hidden_from_files_tab(tmp_path: Path):
    result = CourseSync(MockCanvasClient(), tmp_path).run([148001])
    assert result.stats.failed == 0
    names = {path.name for path in tmp_path.rglob("*") if path.is_file()}
    assert "Hidden lecture note.pdf" in names


def test_stop_skips_remaining_courses(tmp_path: Path):
    events = []
    engine = CourseSync(MockCanvasClient(), tmp_path)

    def on_event(event):
        events.append(event)
        if event.get("type") == "course_start":
            engine.request_stop()

    engine.on_event = on_event
    result = engine.run()
    starts = [event for event in events if event.get("type") == "course_start"]
    assert len(starts) == 1
    assert result.stats.courses == 0
    assert any(event.get("message") == "Stopped" for event in events)
    assert any(event.get("type") == "done" for event in events)


def test_files_tab_403_still_archives_pages_and_links(tmp_path: Path):
    from quercus_sync.canvas import CanvasError

    class NoFilesTab(MockCanvasClient):
        def files(self, course_id: int):
            raise CanvasError("hidden files tab", 403)

    result = CourseSync(NoFilesTab(), tmp_path).run([148001])
    assert result.stats.failed == 0
    names = {path.name for path in tmp_path.rglob("*") if path.is_file()}
    assert "Syllabus.html" in names
    assert "Welcome & how this course runs.html" in names
    assert "Hidden lecture note.pdf" in names
    assert "_manifest.json" in names
