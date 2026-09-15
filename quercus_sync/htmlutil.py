from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any


def html_document(title: str, body_html: str, meta: dict[str, Any] | None = None) -> str:
    rows = ""
    if meta:
        items = "".join(
            f"<li><span>{escape(str(k))}</span><strong>{escape(str(v))}</strong></li>"
            for k, v in meta.items()
            if v not in (None, "")
        )
        rows = f'<ul class="meta">{items}</ul>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0; background: #f7f1e6; color: #1c1914;
      font: 17px/1.55 "Iowan Old Style", "Palatino Linotype", Palatino, serif;
    }}
    main {{ max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.8rem; letter-spacing: -0.03em; margin: 0 0 0.75rem; }}
    .meta {{ list-style: none; padding: 0; margin: 0 0 1.5rem; color: #5c564c; font-size: 0.92rem; }}
    .meta li {{ display: flex; gap: 0.75rem; }}
    .meta span {{ min-width: 7rem; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.72rem; padding-top: 0.2rem; }}
    a {{ color: #8a3b12; }}
    img {{ max-width: 100%; }}
    pre, code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88em; }}
    .canvas-page {{ background: #fffdf8; border: 1px solid #e4d9c6; padding: 1.25rem 1.4rem; border-radius: 10px; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    {rows}
    <article class="canvas-page">{body_html or "<p><em>No body text on Quercus.</em></p>"}</article>
  </main>
</body>
</html>
"""


def iso(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value
