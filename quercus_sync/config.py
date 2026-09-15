from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CANVAS_URL = "https://q.utoronto.ca"
load_dotenv(APP_DIR / ".env")

INCLUDE_CHOICES = (
    "files",
    "modules",
    "pages",
    "assignments",
    "announcements",
    "syllabus",
    "discussions",
    "quizzes",
    "calendar",
)


def data_dir() -> Path:
    return Path(os.environ.get("QUERCUS_DATA_DIR", APP_DIR / "data"))


def default_download_dir() -> Path:
    return Path(os.environ.get("QUERCUS_DOWNLOAD_DIR", APP_DIR / "downloads"))


class AppConfig(BaseModel):
    canvas_url: str = DEFAULT_CANVAS_URL
    token: str = ""
    download_dir: str = ""
    include: list[str] = Field(
        default_factory=lambda: [
            "files",
            "modules",
            "pages",
            "assignments",
            "announcements",
            "syllabus",
            "discussions",
            "quizzes",
            "calendar",
        ]
    )
    demo_mode: bool = True

    def public_dict(self) -> dict[str, Any]:
        token = self.token.strip()
        return {
            "canvas_url": self.canvas_url.rstrip("/"),
            "token_set": bool(token),
            "token_preview": _preview_token(token),
            "download_dir": self.download_dir,
            "include": self.include,
            "demo_mode": self.demo_mode,
        }


def config_path(data_dir_override: Path | None = None) -> Path:
    return (data_dir_override or data_dir()) / "config.json"


def load_config(data_dir_override: Path | None = None) -> AppConfig:
    path = config_path(data_dir_override)
    data: dict[str, Any] = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    env_url = os.environ.get("QUERCUS_CANVAS_URL")
    env_token = os.environ.get("QUERCUS_TOKEN")
    env_dir = os.environ.get("QUERCUS_DOWNLOAD_DIR")
    if env_url:
        data["canvas_url"] = env_url
    if env_token:
        data["token"] = env_token
        data["demo_mode"] = False
    if env_dir:
        data["download_dir"] = env_dir
    config = AppConfig.model_validate(data)
    if not config.download_dir:
        config.download_dir = str(default_download_dir())
    return config


def save_config(config: AppConfig, data_dir_override: Path | None = None) -> None:
    path = config_path(data_dir_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")


def _preview_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "••••"
    return f"{token[:4]}…{token[-3:]}"
