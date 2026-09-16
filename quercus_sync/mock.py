from __future__ import annotations

from copy import deepcopy
from typing import Any

DEMO_USER = {
    "id": 9001,
    "name": "Alex Chen",
    "short_name": "Alex",
    "sortable_name": "Chen, Alex",
    "primary_email": "alex.chen@mail.utoronto.ca",
    "login_id": "chenale8",
}

_LECTURE_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\nQuercus Sync demo lecture notes.\n"
_SLIDES_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\nWeek 03 slides (demo).\n"
_STARTER_ZIP = b"PK\x05\x06" + b"\x00" * 18 + b"demo-starter\n"

COURSES: list[dict[str, Any]] = [
    {
        "id": 148001,
        "name": "Introduction to Computer Science",
        "course_code": "CSC148H5 F",
        "term": {"id": 1, "name": "Fall 2025"},
        "syllabus_body": "<p>Welcome to CSC148. We cover abstract data types, recursion, and a gentle introduction to algorithm analysis.</p><p>Labs are Fridays in DH 2010. Bring a charged laptop.</p>",
        "workflow_state": "available",
        "concluded": False,
        "enrollments": [{"type": "student", "enrollment_state": "active", "user_id": 9001}],
    },
    {
        "id": 102001,
        "name": "Introduction to Mathematical Proofs",
        "course_code": "MAT102H5 F",
        "term": {"id": 1, "name": "Fall 2025"},
        "syllabus_body": "<p>Proof techniques: direct, contradiction, induction. Sets, functions, and relations.</p>",
        "workflow_state": "available",
        "concluded": False,
        "enrollments": [{"type": "student", "enrollment_state": "active", "user_id": 9001}],
    },
    {
        "id": 100001,
        "name": "Introductory Psychology",
        "course_code": "PSY100Y5 Y",
        "term": {"id": 2, "name": "2025-2026"},
        "syllabus_body": "<p>A year-long survey of psychology. Midterms are in-person. Readings are posted weekly.</p>",
        "workflow_state": "available",
        "concluded": False,
        "enrollments": [{"type": "student", "enrollment_state": "active", "user_id": 9001}],
    },
    {
        "id": 210001,
        "name": "The Environment of the Geosphere",
        "course_code": "ERS111H5 F",
        "term": {"id": 1, "name": "Fall 2025"},
        "syllabus_body": "<p>Earth materials, plate tectonics, and surface processes with a UTM field-day in the Credit River valley.</p>",
        "workflow_state": "available",
        "concluded": False,
        "enrollments": [{"type": "student", "enrollment_state": "active", "user_id": 9001}],
    },
    {
        "id": 108001,
        "name": "Introduction to Computer Programming",
        "course_code": "CSC108H5 S",
        "term": {"id": 3, "name": "Winter 2025"},
        "syllabus_body": "<p>Python for people who have not programmed before. The course is over; files stay open until the faculty archive date.</p>",
        "workflow_state": "completed",
        "concluded": True,
        "enrollments": [{"type": "student", "enrollment_state": "completed", "user_id": 9001}],
    },
    {
        "id": 999001,
        "name": "Closed after the term",
        "course_code": "HIS101H5 F",
        "term": {"id": 9, "name": "Fall 2022"},
        "syllabus_body": "",
        "workflow_state": "completed",
        "concluded": True,
        "access_restricted_by_date": True,
        "enrollments": [{"type": "student", "enrollment_state": "completed", "user_id": 9001}],
    },
]


def _file(
    file_id: int,
    course_id: int,
    folder_id: int,
    display: str,
    filename: str,
    folder: str,
    size: int,
    url: str,
) -> dict[str, Any]:
    return {
        "id": file_id,
        "folder_id": folder_id,
        "display_name": display,
        "filename": filename,
        "size": size,
        "url": url,
        "locked_for_user": False,
        "updated_at": "2025-09-10T14:00:00Z",
        "content-type": "application/pdf" if filename.endswith(".pdf") else "application/octet-stream",
        "_folder": folder,
    }


FILES: dict[int, list[dict[str, Any]]] = {
    148001: [
        _file(
            11,
            148001,
            1,
            "Week 01 — Python recap.pdf",
            "week01.pdf",
            "course files/Lectures",
            len(_LECTURE_PDF),
            "/demo-files/csc148-week01.pdf",
        ),
        _file(
            12,
            148001,
            1,
            "Week 03 — Recursion slides.pdf",
            "week03-slides.pdf",
            "course files/Lectures",
            len(_SLIDES_PDF),
            "/demo-files/csc148-week03.pdf",
        ),
        _file(
            13,
            148001,
            2,
            "Lab 2 starter.zip",
            "lab2-starter.zip",
            "course files/Labs",
            len(_STARTER_ZIP),
            "/demo-files/csc148-lab2.zip",
        ),
        _file(
            14,
            148001,
            3,
            "Course outline.pdf",
            "outline.pdf",
            "course files",
            len(_LECTURE_PDF),
            "/demo-files/csc148-outline.pdf",
        ),
    ],
    102001: [
        _file(
            21,
            102001,
            4,
            "Lecture 04 — Induction.pdf",
            "lec04.pdf",
            "course files/Lectures",
            len(_LECTURE_PDF),
            "/demo-files/mat102-lec04.pdf",
        ),
        _file(
            22,
            102001,
            5,
            "Problem set 2.pdf",
            "ps2.pdf",
            "course files/Problem sets",
            len(_SLIDES_PDF),
            "/demo-files/mat102-ps2.pdf",
        ),
    ],
    100001: [
        _file(
            31,
            100001,
            6,
            "Chapter 3 reading notes.pdf",
            "ch3.pdf",
            "course files/Readings",
            len(_LECTURE_PDF),
            "/demo-files/psy100-ch3.pdf",
        ),
        _file(
            32,
            100001,
            7,
            "Research participation info.pdf",
            "sona.pdf",
            "course files",
            len(_SLIDES_PDF),
            "/demo-files/psy100-sona.pdf",
        ),
    ],
    210001: [
        _file(
            41,
            210001,
            8,
            "Field day briefing.pdf",
            "field-day.pdf",
            "course files/Field",
            len(_LECTURE_PDF),
            "/demo-files/ers111-field.pdf",
        ),
        _file(
            42,
            210001,
            9,
            "Mineral ID chart.pdf",
            "minerals.pdf",
            "course files/Labs",
            len(_SLIDES_PDF),
            "/demo-files/ers111-minerals.pdf",
        ),
    ],
    108001: [
        _file(
            51,
            108001,
            10,
            "Week 08 lists.pdf",
            "week08.pdf",
            "course files/Lectures",
            len(_LECTURE_PDF),
            "/demo-files/csc108-week08.pdf",
        ),
        _file(
            52,
            108001,
            11,
            "Final exam seating.pdf",
            "seating.pdf",
            "course files",
            len(_SLIDES_PDF),
            "/demo-files/csc108-seating.pdf",
        ),
    ],
}

MODULE_ONLY_FILES: dict[int, dict[str, Any]] = {
    59: _file(
        59,
        108001,
        10,
        "Review session handout.pdf",
        "review.pdf",
        "course files/From modules",
        len(_SLIDES_PDF),
        "/demo-files/csc108-review.pdf",
    ),
    77: _file(
        77,
        148001,
        3,
        "Hidden lecture note.pdf",
        "hidden-note.pdf",
        "course files/From pages",
        len(_LECTURE_PDF),
        "/demo-files/csc148-hidden.pdf",
    ),
    78: _file(
        78,
        148001,
        3,
        "Week 1 notes.pdf",
        "week1-notes.pdf",
        "course files/From pages",
        len(_LECTURE_PDF),
        "/demo-files/csc148-week1-guide.pdf",
    ),
}

FOLDERS: dict[int, list[dict[str, Any]]] = {
    148001: [
        {"id": 1, "full_name": "course files/Lectures", "name": "Lectures"},
        {"id": 2, "full_name": "course files/Labs", "name": "Labs"},
        {"id": 3, "full_name": "course files", "name": "course files"},
    ],
    102001: [
        {"id": 4, "full_name": "course files/Lectures", "name": "Lectures"},
        {"id": 5, "full_name": "course files/Problem sets", "name": "Problem sets"},
    ],
    100001: [
        {"id": 6, "full_name": "course files/Readings", "name": "Readings"},
        {"id": 7, "full_name": "course files", "name": "course files"},
    ],
    210001: [
        {"id": 8, "full_name": "course files/Field", "name": "Field"},
        {"id": 9, "full_name": "course files/Labs", "name": "Labs"},
    ],
    108001: [
        {"id": 10, "full_name": "course files/Lectures", "name": "Lectures"},
        {"id": 11, "full_name": "course files", "name": "course files"},
    ],
}

MODULES: dict[int, list[dict[str, Any]]] = {
    148001: [
        {
            "id": 1,
            "name": "Week 1 — Getting oriented",
            "position": 1,
            "items": [
                {"id": 101, "title": "Welcome & how this course runs", "type": "Page", "page_url": "welcome"},
                {"id": 102, "title": "Week 01 — Python recap.pdf", "type": "File", "content_id": 11},
                {
                    "id": 106,
                    "title": "Lecture recording",
                    "type": "ExternalUrl",
                    "external_url": "https://www.youtube.com/watch?v=csc148-week1",
                },
            ],
        },
        {
            "id": 2,
            "name": "Week 3 — Recursion",
            "position": 2,
            "items": [
                {"id": 103, "title": "Tracing recursive calls", "type": "Page", "page_url": "tracing-recursion"},
                {"id": 104, "title": "Week 03 — Recursion slides.pdf", "type": "File", "content_id": 12},
                {"id": 105, "title": "Lab 2", "type": "Assignment", "content_id": 501},
            ],
        },
    ],
    102001: [
        {
            "id": 3,
            "name": "Unit 2 — Induction",
            "position": 1,
            "items": [
                {"id": 201, "title": "What induction is for", "type": "Page", "page_url": "induction"},
                {"id": 202, "title": "Lecture 04 — Induction.pdf", "type": "File", "content_id": 21},
            ],
        }
    ],
    100001: [
        {
            "id": 4,
            "name": "Research methods",
            "position": 1,
            "items": [
                {"id": 301, "title": "How to read a methods section", "type": "Page", "page_url": "methods"},
            ],
        }
    ],
    210001: [
        {
            "id": 5,
            "name": "Field day",
            "position": 1,
            "items": [
                {"id": 401, "title": "What to bring", "type": "Page", "page_url": "field-kit"},
                {"id": 402, "title": "Field day briefing.pdf", "type": "File", "content_id": 41},
            ],
        }
    ],
    108001: [
        {
            "id": 6,
            "name": "Exam review",
            "position": 1,
            "items": [
                {"id": 501, "title": "Review session handout.pdf", "type": "File", "content_id": 59},
            ],
        }
    ],
}

PAGES: dict[int, dict[str, dict[str, Any]]] = {
    148001: {
        "welcome": {
            "url": "welcome",
            "title": "Welcome & how this course runs",
            "body": "<p>Office hours are Tuesday 14:00–16:00 in DH 3072. Use Piazza for non-personal questions.</p><p>You are expected to attempt the pre-lab before Friday.</p><p><a href=\"https://q.utoronto.ca/courses/148001/files/77/download?download_frd=1\">Hidden lecture note</a></p><p><a href=\"https://q.utoronto.ca/courses/148001/pages/week-1-guide\">Week 1 guide</a></p><p><a href=\"https://www.youtube.com/watch?v=csc148-home\">Home recording</a></p>",
            "updated_at": "2025-09-02T12:00:00Z",
        },
        "week-1-guide": {
            "url": "week-1-guide",
            "title": "Week 1 guide",
            "hidden_from_index": True,
            "body": "<p>Read the notes, then the recording.</p><p><a href=\"https://q.utoronto.ca/courses/148001/files/78/download?download_frd=1\">Week 1 notes</a></p><iframe src=\"https://play.library.utoronto.ca/watch/demo-week1\"></iframe>",
            "updated_at": "2025-09-03T12:00:00Z",
        },
        "tracing-recursion": {
            "url": "tracing-recursion",
            "title": "Tracing recursive calls",
            "body": "<p>Draw the call stack. Label the base case. Then fill in return values on the way back up.</p><ol><li>Write the base case first.</li><li>Assume the recursive call is correct.</li><li>Combine.</li></ol>",
            "updated_at": "2025-09-16T12:00:00Z",
        },
    },
    102001: {
        "induction": {
            "url": "induction",
            "title": "What induction is for",
            "body": "<p>Induction is a way of proving a statement for every natural number by proving a base case and an inductive step.</p>",
            "updated_at": "2025-09-18T12:00:00Z",
        }
    },
    100001: {
        "methods": {
            "url": "methods",
            "title": "How to read a methods section",
            "body": "<p>Look for: sample, measures, procedure, and what was actually compared. Correlation is not a design.</p>",
            "updated_at": "2025-09-12T12:00:00Z",
        }
    },
    210001: {
        "field-kit": {
            "url": "field-kit",
            "title": "What to bring",
            "body": "<ul><li>Closed-toe shoes</li><li>Water</li><li>Notebook (Rite in the Rain if you have one)</li><li>Pencil</li></ul>",
            "updated_at": "2025-09-20T12:00:00Z",
        }
    },
    108001: {
        "after-the-term": {
            "url": "after-the-term",
            "title": "What stays up after April",
            "body": "<p>Lecture PDFs remain until August. The exam paper is not posted.</p>",
            "updated_at": "2025-04-30T12:00:00Z",
        }
    },
}

ASSIGNMENTS: dict[int, list[dict[str, Any]]] = {
    148001: [
        {
            "id": 501,
            "name": "Lab 2 — Recursion",
            "due_at": "2025-09-26T22:00:00Z",
            "points_possible": 10,
            "description": "<p>Implement <code>sum_nested</code> and write two of your own tests. Submit on MarkUs.</p>",
        },
        {
            "id": 502,
            "name": "Exercise 1 — ADTs",
            "due_at": "2025-10-03T22:00:00Z",
            "points_possible": 8,
            "description": "<p>Stacks vs queues: pick the right structure for each scenario and justify in two sentences.</p>",
        },
    ],
    102001: [
        {
            "id": 601,
            "name": "Problem set 2",
            "due_at": "2025-09-29T22:00:00Z",
            "points_possible": 20,
            "description": "<p>Submit a single PDF. Write in complete sentences. Box the final statement of each proof.</p>",
        }
    ],
    100001: [
        {
            "id": 701,
            "name": "Reflection 1",
            "due_at": "2025-10-08T22:00:00Z",
            "points_possible": 5,
            "description": "<p>300 words on a study from this unit. Cite in APA.</p>",
        }
    ],
    210001: [
        {
            "id": 801,
            "name": "Field notebook scan",
            "due_at": "2025-10-06T22:00:00Z",
            "points_possible": 15,
            "description": "<p>Upload a PDF scan of your field notes plus the mineral ID table from lab 3.</p>",
        }
    ],
    108001: [
        {
            "id": 901,
            "name": "Lab 9 — dictionaries",
            "due_at": "2025-03-21T22:00:00Z",
            "points_possible": 10,
            "description": "<p>Submit on MarkUs. Starter is attached.</p>",
            "attachments": [
                {
                    "id": 60,
                    "filename": "lab9-starter.zip",
                    "display_name": "lab9-starter.zip",
                    "url": "/demo-files/csc108-lab9.zip",
                    "size": len(_STARTER_ZIP),
                    "locked_for_user": False,
                    "_folder": "course files/From assignments/Lab 9 — dictionaries",
                }
            ],
        }
    ],
}

ANNOUNCEMENTS: dict[int, list[dict[str, Any]]] = {
    148001: [
        {
            "id": 9001,
            "title": "Lab rooms this Friday",
            "message": "<p>Lab 2 is in DH 2010, not the overflow room. Bring headphones if you want to watch the tracing video without speakers.</p>",
            "posted_at": "2025-09-18T15:00:00Z",
        }
    ],
    102001: [
        {
            "id": 9002,
            "title": "Office hours extra session",
            "message": "<p>There will be a drop-in proof clinic Thursday 17:00 in the Math Help Centre.</p>",
            "posted_at": "2025-09-17T11:00:00Z",
        }
    ],
    100001: [
        {
            "id": 9003,
            "title": "SONA credits reminder",
            "message": "<p>Research participation hours open next Monday. The alternative written assignment is posted under Files.</p>",
            "posted_at": "2025-09-14T09:00:00Z",
        }
    ],
    210001: [
        {
            "id": 9004,
            "title": "Field day weather call",
            "message": "<p>We are still on for Saturday. If Environment Canada issues a thunderstorm warning before 07:00, we postpone to Sunday.</p>",
            "posted_at": "2025-09-19T18:00:00Z",
        }
    ],
    108001: [
        {
            "id": 9005,
            "title": "Marks posted",
            "message": "<p>Final marks are on ACORN. Lecture files stay up on Quercus until 31 August.</p>",
            "posted_at": "2025-05-12T10:00:00Z",
        }
    ],
}

DISCUSSIONS: dict[int, list[dict[str, Any]]] = {
    148001: [
        {
            "id": 3001,
            "title": "Lab 2 clarifications",
            "message": "<p>Post helper questions here. Do not paste full solutions.</p>",
            "posted_at": "2025-09-16T10:00:00Z",
        }
    ],
    102001: [],
    100001: [],
    210001: [],
    108001: [],
}

DISCUSSION_VIEWS: dict[tuple[int, int], dict[str, Any]] = {
    (148001, 3001): {
        "view": [
            {
                "id": 1,
                "user_id": 9001,
                "message": "<p>Does the nested list only contain ints, or can it mix types?</p>",
                "created_at": "2025-09-16T11:00:00Z",
            },
            {
                "id": 2,
                "user_id": 42,
                "message": "<p>Only ints and other lists, as in the docstring.</p>",
                "created_at": "2025-09-16T11:20:00Z",
            },
        ]
    }
}

FILE_BYTES: dict[str, bytes] = {
    "/demo-files/csc148-week01.pdf": _LECTURE_PDF,
    "/demo-files/csc148-week03.pdf": _SLIDES_PDF,
    "/demo-files/csc148-lab2.zip": _STARTER_ZIP,
    "/demo-files/csc148-outline.pdf": _LECTURE_PDF,
    "/demo-files/mat102-lec04.pdf": _LECTURE_PDF,
    "/demo-files/mat102-ps2.pdf": _SLIDES_PDF,
    "/demo-files/psy100-ch3.pdf": _LECTURE_PDF,
    "/demo-files/psy100-sona.pdf": _SLIDES_PDF,
    "/demo-files/ers111-field.pdf": _LECTURE_PDF,
    "/demo-files/ers111-minerals.pdf": _SLIDES_PDF,
    "/demo-files/csc108-week08.pdf": _LECTURE_PDF,
    "/demo-files/csc108-seating.pdf": _SLIDES_PDF,
    "/demo-files/csc108-review.pdf": _SLIDES_PDF,
    "/demo-files/csc108-lab9.zip": _STARTER_ZIP,
    "/demo-files/csc148-hidden.pdf": _LECTURE_PDF,
    "/demo-files/csc148-week1-guide.pdf": _LECTURE_PDF,
}


class MockCanvasClient:
    """In-memory Canvas stand-in so the app is usable without a Quercus token."""

    def __init__(self, base_url: str = "https://q.utoronto.ca", token: str = "demo") -> None:
        self.base_url = base_url
        self.token = token

    def close(self) -> None:
        return None

    def __enter__(self) -> MockCanvasClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def me(self) -> dict[str, Any]:
        return deepcopy(DEMO_USER)

    def courses(self) -> list[dict[str, Any]]:
        return deepcopy(COURSES)

    def files(self, course_id: int) -> list[dict[str, Any]]:
        return deepcopy(FILES.get(course_id, []))

    def file(self, file_id: int) -> dict[str, Any]:
        for rows in FILES.values():
            for item in rows:
                if item["id"] == file_id:
                    return deepcopy(item)
        extra = MODULE_ONLY_FILES.get(file_id)
        if extra:
            return deepcopy(extra)
        raise FileNotFoundError(file_id)

    def folder_files(self, folder_id: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for course_files in FILES.values():
            for item in course_files:
                if item.get("folder_id") == folder_id:
                    rows.append(deepcopy(item))
        return rows

    def folders(self, course_id: int) -> list[dict[str, Any]]:
        return deepcopy(FOLDERS.get(course_id, []))

    def front_page(self, course_id: int) -> dict[str, Any] | None:
        pages = PAGES.get(course_id) or {}
        if not pages:
            return None
        first = next(iter(pages.values()))
        return deepcopy(first)

    def quizzes(self, course_id: int) -> list[dict[str, Any]]:
        return []

    def calendar_events(self, course_id: int) -> list[dict[str, Any]]:
        return []

    def modules(self, course_id: int) -> list[dict[str, Any]]:
        return deepcopy(MODULES.get(course_id, []))

    def pages(self, course_id: int) -> list[dict[str, Any]]:
        rows = []
        for page in (PAGES.get(course_id) or {}).values():
            if page.get("hidden_from_index"):
                continue
            rows.append(deepcopy(page))
        return rows

    def page(self, course_id: int, slug: str) -> dict[str, Any] | None:
        item = (PAGES.get(course_id) or {}).get(slug)
        if not item:
            return None
        return deepcopy(item)

    def assignments(self, course_id: int) -> list[dict[str, Any]]:
        return deepcopy(ASSIGNMENTS.get(course_id, []))

    def announcements(self, course_id: int) -> list[dict[str, Any]]:
        return deepcopy(ANNOUNCEMENTS.get(course_id, []))

    def discussions(self, course_id: int) -> list[dict[str, Any]]:
        return deepcopy(DISCUSSIONS.get(course_id, []))

    def discussion(self, course_id: int, topic_id: int) -> dict[str, Any]:
        return deepcopy(DISCUSSION_VIEWS.get((course_id, topic_id), {"view": []}))

    def download(self, url: str) -> tuple[bytes, str]:
        body = FILE_BYTES.get(url)
        if body is None:
            raise FileNotFoundError(url)
        if url.endswith(".zip"):
            return body, "application/zip"
        return body, "application/pdf"
