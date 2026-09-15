from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

CANVAS_HOST_RE = re.compile(
    r"(utoronto\.ca|instructure\.com|canvaslms\.com|canvas\.edu)$",
    re.I,
)


class CanvasError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CanvasClient:
    """Thin Canvas REST client. Auth is only sent to Canvas hosts, never to S3."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        if not self.token:
            raise CanvasError("Missing Canvas access token.")
        kwargs: dict[str, Any] = {}
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0, read=180.0),
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=0, max_connections=20),
            headers={
                "Accept": "application/json",
                "User-Agent": "quercus-sync/0.1 (personal course archive)",
                "Connection": "close",
            },
            **kwargs,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CanvasClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._request("GET", path, params=params)
        if response.status_code == 401:
            raise CanvasError("Quercus rejected this token. Create a new access token under Account → Settings.", 401)
        if response.status_code == 403:
            raise CanvasError("Quercus refused this request (forbidden or rate limited).", 403)
        if response.status_code >= 400:
            raise CanvasError(f"Canvas API {response.status_code} for {path}", response.status_code)
        if not response.content:
            return None
        return response.json()

    def paginate(self, path: str, params: dict[str, Any] | None = None, *, missing_ok: bool = False) -> list[Any]:
        items: list[Any] = []
        query = {"per_page": 100, **(params or {})}
        url: str | None = path
        first = True
        while url:
            response = self._request("GET", url, params=query if first else None)
            if response.status_code >= 400:
                if (
                    missing_ok
                    and response.status_code in {401, 403, 404}
                    and "Rate Limit" not in (response.text or "")
                ):
                    return items
                raise CanvasError(f"Canvas API {response.status_code} for {url}", response.status_code)
            payload = response.json()
            if isinstance(payload, list):
                items.extend(payload)
            else:
                items.append(payload)
            url = _next_link(response.headers.get("Link"))
            first = False
        return items

    def me(self) -> dict[str, Any]:
        return self.get_json("/api/v1/users/self")

    def courses(self) -> list[dict[str, Any]]:
        """Courses this user can still open: current and concluded enrollments.

        Canvas defaults to active-only. Students keep read access to many past
        terms; those show up when enrollment_state includes completed.
        """
        return self.paginate(
            "/api/v1/courses",
            {
                "enrollment_state[]": ["active", "completed"],
                "include[]": ["term", "syllabus_body", "concluded", "enrollments"],
            },
        )

    def file(self, file_id: int) -> dict[str, Any]:
        return self.get_json(f"/api/v1/files/{file_id}")

    def files(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(
            f"/api/v1/courses/{course_id}/files",
            {"sort": "updated_at"},
            missing_ok=True,
        )

    def folder_files(self, folder_id: int) -> list[dict[str, Any]]:
        return self.paginate(
            f"/api/v1/folders/{folder_id}/files",
            {"sort": "updated_at"},
            missing_ok=True,
        )

    def folders(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(f"/api/v1/courses/{course_id}/folders", missing_ok=True)

    def front_page(self, course_id: int) -> dict[str, Any] | None:
        response = self._request("GET", f"/api/v1/courses/{course_id}/front_page")
        if response.status_code in {404, 403}:
            return None
        if response.status_code >= 400:
            raise CanvasError(
                f"Canvas API {response.status_code} for /api/v1/courses/{course_id}/front_page",
                response.status_code,
            )
        if not response.content:
            return None
        return response.json()

    def quizzes(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(f"/api/v1/courses/{course_id}/quizzes", missing_ok=True)

    def calendar_events(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(
            "/api/v1/calendar_events",
            {
                "type": "event",
                "context_codes[]": f"course_{course_id}",
                "all_events": True,
            },
            missing_ok=True,
        )

    def modules(self, course_id: int) -> list[dict[str, Any]]:
        modules = self.paginate(
            f"/api/v1/courses/{course_id}/modules",
            {"include[]": ["items"]},
            missing_ok=True,
        )
        for module in modules:
            if not module.get("items") and module.get("items_count"):
                module["items"] = self.paginate(
                    f"/api/v1/courses/{course_id}/modules/{module['id']}/items",
                    missing_ok=True,
                )
        return modules

    def pages(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(
            f"/api/v1/courses/{course_id}/pages",
            {"sort": "title"},
            missing_ok=True,
        )

    def page(self, course_id: int, slug: str) -> dict[str, Any]:
        return self.get_json(f"/api/v1/courses/{course_id}/pages/{slug}")

    def assignments(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(
            f"/api/v1/courses/{course_id}/assignments",
            {"include[]": ["overrides"]},
            missing_ok=True,
        )

    def announcements(self, course_id: int) -> list[dict[str, Any]]:
        # Canvas defaults to the last 14 days. Pass an open window so old posts still archive.
        return self.paginate(
            "/api/v1/announcements",
            {
                "context_codes[]": f"course_{course_id}",
                "start_date": "1970-01-01",
                "end_date": "2100-12-31",
            },
            missing_ok=True,
        )

    def discussions(self, course_id: int) -> list[dict[str, Any]]:
        return self.paginate(
            f"/api/v1/courses/{course_id}/discussion_topics",
            missing_ok=True,
        )

    def discussion(self, course_id: int, topic_id: int) -> dict[str, Any]:
        return self.get_json(
            f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}/view",
        )

    def download(self, url: str) -> tuple[bytes, str]:
        """Follow Canvas redirects; drop the bearer token once we leave Canvas."""
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                return self._download_once(url)
            except (httpx.TransportError, OSError) as exc:
                last_error = exc
                time.sleep(min(1.5 * (attempt + 1), 8))
        raise CanvasError(f"Download failed for {url}: {last_error}")

    def _download_once(self, url: str) -> tuple[bytes, str]:
        current = url
        auth = True
        for _ in range(8):
            headers = {"Connection": "close"}
            if auth:
                headers["Authorization"] = f"Bearer {self.token}"
            if current.startswith("/"):
                response = self._client.get(current, headers=headers)
            else:
                response = httpx.get(
                    current,
                    headers=headers,
                    follow_redirects=False,
                    timeout=httpx.Timeout(30.0, read=180.0),
                )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise CanvasError("Redirect without Location header.")
                current = location
                auth = _is_canvas_host(current, self.base_url)
                continue
            if response.status_code >= 400:
                raise CanvasError(f"Download failed ({response.status_code}) for {url}", response.status_code)
            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.content, content_type
        raise CanvasError(f"Too many redirects downloading {url}")

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"}
        for attempt in range(4):
            response = self._client.request(method, path, params=params, headers=headers)
            if response.status_code == 429 or (
                response.status_code == 403 and "Rate Limit" in response.text
            ):
                retry = float(response.headers.get("Retry-After", 1.5 * (attempt + 1)))
                import time

                time.sleep(min(retry, 20))
                continue
            return response
        return response


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        if 'rel="next"' in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)
    return None


def _is_canvas_host(url: str, base_url: str) -> bool:
    host = urlparse(url).hostname or ""
    base_host = urlparse(base_url).hostname or ""
    if host and base_host and host == base_host:
        return True
    return bool(CANVAS_HOST_RE.search(host))
