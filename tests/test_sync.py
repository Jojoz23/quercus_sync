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
