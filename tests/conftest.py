from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_app_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("QUERCUS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("QUERCUS_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.delenv("QUERCUS_TOKEN", raising=False)
    monkeypatch.delenv("QUERCUS_CANVAS_URL", raising=False)
