from pathlib import Path

from quercus_sync.paths import course_folder, safe_name, unique_path


def test_safe_name_strips_paths_and_junk():
    assert "/" not in safe_name("week 1 / intro: slides?")
    assert safe_name("...") == "untitled"
    assert len(safe_name("a" * 200 + ".pdf")) <= 120


def test_course_folder_avoids_duplicating_code():
    assert course_folder("CSC148H5 F", "CSC148H5 F Introduction") == "CSC148H5 F Introduction"
    assert "—" in course_folder("MAT102H5 F", "Introduction to Mathematical Proofs")


def test_unique_path(tmp_path: Path):
    target = tmp_path / "notes.pdf"
    target.write_text("one")
    second = unique_path(target)
    assert second.name == "notes (2).pdf"


def test_clip_path_shortens_long_windows_names(tmp_path: Path):
    from quercus_sync.paths import clip_path

    long = tmp_path / ("folder " + "x" * 80) / ("file " + "y" * 80 + ".pdf")
    clipped = clip_path(long, limit=len(str(tmp_path)) + 40)
    assert len(str(clipped)) <= len(str(tmp_path)) + 40


def test_clip_path_shortens_leaf_and_keeps_course_folder(tmp_path: Path):
    from quercus_sync.paths import clip_path

    course = tmp_path / "MAT 137 F_W 2022-2023 - All Sections"
    dest = course / "Announcements" / ("2023-03-29 Tomorrow lecture " + "x" * 90 + ".html")
    budget = len(str(course)) + 36
    clipped = clip_path(dest, limit=budget, keep_prefix=course)
    assert clipped.parts[-3] == course.name
    assert str(clipped).startswith(str(course))
    assert len(str(clipped)) <= budget or clipped.name != dest.name


def test_merge_truncated_course_folders(tmp_path: Path):
    from quercus_sync.cleanup import merge_truncated_folders

    term = tmp_path / "2023 Winter"
    keep = term / "CCT112H5 S LEC0101 20231_Introduction to Management in the Networked Information Economy"
    stub = term / "CCT112H5 S LEC0101 20231_Introduction to Management in the Netwo"
    other = term / "ISP100H5 S LEC0113 20231_Writing for University and Beyond_ Writing About Writing"
    (keep / "Files").mkdir(parents=True)
    (keep / "Files" / "shared.pdf").write_text("canonical")
    (stub / "Announcements").mkdir(parents=True)
    (stub / "Announcements" / "unique.html").write_text("only in stub")
    (stub / "Files").mkdir()
    (stub / "Files" / "shared.pdf").write_text("old")
    (other / "Pages").mkdir(parents=True)
    (other / "Pages" / "home.html").write_text("keep me")

    report = merge_truncated_folders(tmp_path)
    assert len(report) == 1
    assert report[0]["copied"] == 1
    assert not stub.exists()
    assert (keep / "Announcements" / "unique.html").read_text() == "only in stub"
    assert (keep / "Files" / "shared.pdf").read_text() == "canonical"
    assert other.exists()
