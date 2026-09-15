from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from quercus_sync.config import AppConfig, load_config, save_config
from quercus_sync.mock import MockCanvasClient
from quercus_sync.sync import CourseSync, course_access, library_tree

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Quercus Sync", version="0.1.0")
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

_jobs: dict[str, "_Job"] = {}


class _Job:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.done = False


class SettingsIn(BaseModel):
    canvas_url: str = "https://q.utoronto.ca"
    token: str | None = None
    download_dir: str | None = None
    include: list[str] | None = None
    demo_mode: bool | None = None
    clear_token: bool = False


class SyncIn(BaseModel):
    course_ids: list[int] = Field(default_factory=list)
    demo: bool | None = None


def _make_client(config: AppConfig, force_demo: bool | None = None):
    demo = config.demo_mode if force_demo is None else force_demo
    if demo or not config.token:
        return MockCanvasClient(config.canvas_url)
    from quercus_sync.canvas import CanvasClient

    return CanvasClient(config.canvas_url, config.token)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return load_config().public_dict()


@app.put("/api/config")
def put_config(payload: SettingsIn) -> dict[str, Any]:
    config = load_config()
    config.canvas_url = payload.canvas_url.rstrip("/") or config.canvas_url
    if payload.clear_token:
        config.token = ""
        config.demo_mode = True
    elif payload.token:
        config.token = payload.token.strip()
        config.demo_mode = False
    if payload.download_dir:
        config.download_dir = payload.download_dir
    if payload.include is not None:
        config.include = payload.include
    if payload.demo_mode is not None and not payload.token:
        config.demo_mode = payload.demo_mode
    save_config(config)
    return config.public_dict()


@app.get("/api/me")
def me() -> dict[str, Any]:
    config = load_config()
    client = _make_client(config)
    try:
        profile = client.me()
        return {
            "name": profile.get("name"),
            "login": profile.get("login_id") or profile.get("primary_email"),
            "demo": config.demo_mode or not config.token,
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/courses")
def courses() -> dict[str, Any]:
    config = load_config()
    client = _make_client(config)
    try:
        items = CourseSync(client, Path(config.download_dir)).list_courses()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "demo": config.demo_mode or not config.token,
        "courses": [
            {
                "id": c["id"],
                "name": c.get("name"),
                "course_code": c.get("course_code"),
                "term": (c.get("term") or {}).get("name"),
                "access": course_access(c),
            }
            for c in items
        ],
    }


@app.post("/api/sync")
async def start_sync(payload: SyncIn) -> dict[str, str]:
    job_id = str(uuid4())
    job = _Job()
    _jobs[job_id] = job
    loop = asyncio.get_running_loop()

    def emit(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(job.queue.put_nowait, event)

    def work() -> None:
        config = load_config()
        demo = payload.demo if payload.demo is not None else (config.demo_mode or not config.token)
        client = _make_client(config, force_demo=demo)
        engine = CourseSync(
            client,
            Path(config.download_dir),
            include=config.include,
            on_event=emit,
        )
        try:
            engine.run(payload.course_ids or None)
        except Exception as exc:  # noqa: BLE001
            emit({"type": "error", "message": str(exc)})
            emit({"type": "done", "stats": engine.stats.as_dict(), "errors": [str(exc)]})
        finally:
            job.done = True
            loop.call_soon_threadsafe(job.queue.put_nowait, None)

    loop.run_in_executor(None, work)
    return {"job_id": job_id}


@app.get("/api/sync/{job_id}/events")
async def sync_events(job_id: str) -> StreamingResponse:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown sync job")

    async def stream():
        while True:
            event = await job.queue.get()
            if event is None:
                yield "event: close\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/library")
def library() -> dict[str, Any]:
    config = load_config()
    root = Path(config.download_dir)
    return {"root": str(root), "items": library_tree(root)}


@app.get("/api/library/file")
def library_file(path: str) -> FileResponse:
    config = load_config()
    root = Path(config.download_dir).resolve()
    target = (root / path).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)
