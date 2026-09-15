from quercus_sync.canvas import _is_canvas_host, _next_link


def test_next_link_parses_canvas_header():
    header = '<https://q.utoronto.ca/api/v1/courses?page=2>; rel="next", <https://q.utoronto.ca/api/v1/courses?page=1>; rel="current"'
    assert _next_link(header).endswith("page=2")
    assert _next_link(None) is None


def test_auth_stays_on_canvas_hosts_only():
    base = "https://q.utoronto.ca"
    assert _is_canvas_host("https://q.utoronto.ca/files/1/download", base)
    assert _is_canvas_host("https://utm.instructure.com/files/1", base)
    assert not _is_canvas_host("https://canvas-files.s3.amazonaws.com/abc", base)
