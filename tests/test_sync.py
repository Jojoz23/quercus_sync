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
    from quercus_sync.htmlutil import canvas_file_ids, canvas_page_slugs, html_external_links

    html = '<a href="https://q.utoronto.ca/courses/1/files/77/download?download_frd=1">note</a>'
    assert canvas_file_ids(html) == {77}
    assert canvas_file_ids("") == set()
    assert canvas_page_slugs(
        '<a href="https://q.utoronto.ca/courses/1/pages/week-1-guide">guide</a>'
        '<a href="/courses/1/wiki/induction">old</a>'
    ) == {"week-1-guide", "induction"}
    links = html_external_links(
        '<a href="https://www.youtube.com/watch?v=abc">rec</a>'
        '<iframe src="https://play.library.utoronto.ca/watch/x"></iframe>'
        '<a href="https://q.utoronto.ca/courses/1/files/77/download">file</a>'
    )
    assert [url for url, _host in links] == [
        "https://www.youtube.com/watch?v=abc",
        "https://play.library.utoronto.ca/watch/x",
    ]


def test_rewrite_canvas_hrefs_to_local_files(tmp_path: Path):
    from quercus_sync.htmlutil import rewrite_local_links

    html_path = tmp_path / "Pages" / "Week 1 Guide.html"
    html_path.parent.mkdir()
    pdf = tmp_path / "Files" / "From pages" / "week_1.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"pdf")
    other = tmp_path / "Pages" / "Week 2 Guide.html"
    other.write_text("page", encoding="utf-8")
    html = (
        '<a title="week_1.pdf" href="https://q.utoronto.ca/courses/1/files/99?wrap=1">in-class</a>'
        '<a href="https://q.utoronto.ca/courses/1/pages/week-2-guide">next</a>'
        '<a href="https://www.youtube.com/watch?v=abc">rec</a>'
    )
    updated = rewrite_local_links(
        html,
        html_path,
        file_by_id={},
        page_by_slug={"week-2-guide": other},
        files_by_name={"week_1.pdf": [pdf]},
    )
    assert "q.utoronto.ca/courses/1/files/99" not in updated
    assert "week_1.pdf" in updated
    assert "Week%202%20Guide.html" in updated or "Week 2 Guide.html" in updated
    assert "https://www.youtube.com/watch?v=abc" in updated
    shared = (
        '<a title="syllabus" href="https://q.utoronto.ca/courses/1/files/44/download">Syllabus</a>'
        '<a title="week_1.pdf" href="https://q.utoronto.ca/courses/1/files/44?wrap=1">pdf</a>'
    )
    both = rewrite_local_links(
        shared,
        html_path,
        file_by_id={},
        page_by_slug={},
        files_by_name={"week_1.pdf": [pdf]},
    )
    assert both.count("q.utoronto.ca/courses/1/files/44") == 0


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


def test_crawls_hidden_wiki_pages_and_lists_other_links(tmp_path: Path):
    result = CourseSync(MockCanvasClient(), tmp_path).run([148001])
    assert result.stats.failed == 0
    names = {path.name for path in tmp_path.rglob("*") if path.is_file()}
    assert "Week 1 guide.html" in names
    assert "Week 1 notes.pdf" in names
    links = next(path for path in tmp_path.rglob("Links.md"))
    text = links.read_text(encoding="utf-8")
    assert "youtube.com/watch?v=csc148-home" in text
    assert "play.library.utoronto.ca/watch/demo-week1" in text
    assert any(path.name == "Lecture recording.url.txt" for path in tmp_path.rglob("*.url.txt"))


def test_html_hrefs_point_at_local_copies(tmp_path: Path):
    CourseSync(MockCanvasClient(), tmp_path).run([148001])
    welcome = next(path for path in tmp_path.rglob("Welcome*.html"))
    text = welcome.read_text(encoding="utf-8")
    assert "q.utoronto.ca/courses/148001/files/77" not in text
    assert "Hidden%20lecture%20note.pdf" in text or "Hidden lecture note.pdf" in text
    assert "Week%201%20guide.html" in text or "Week 1 guide.html" in text
    assert "https://www.youtube.com/watch?v=csc148-home" in text
    guide = next(path for path in tmp_path.rglob("Week 1 guide.html"))
    guide_text = guide.read_text(encoding="utf-8")
    assert "q.utoronto.ca/courses/148001/files/78" not in guide_text
    assert "Week%201%20notes.pdf" in guide_text or "Week 1 notes.pdf" in guide_text
    assert "play.library.utoronto.ca/watch/demo-week1" in guide_text


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
