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
