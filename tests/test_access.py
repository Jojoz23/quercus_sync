from quercus_sync.sync import course_access, is_accessible_course


def test_date_locked_courses_are_skipped():
    assert not is_accessible_course(
        {"id": 1, "name": "Old", "access_restricted_by_date": True}
    )
    assert is_accessible_course({"id": 2, "name": "Open", "workflow_state": "completed"})


def test_concluded_enrolment_is_past():
    assert (
        course_access(
            {
                "concluded": True,
                "enrollments": [{"enrollment_state": "completed"}],
            }
        )
        == "past"
    )
    assert (
        course_access({"enrollments": [{"enrollment_state": "active"}]})
        == "current"
    )
