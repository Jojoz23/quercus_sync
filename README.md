# Quercus Sync

A local archive of **your** University of Toronto Mississauga courses on [Quercus](https://q.utoronto.ca).

Quercus is Canvas. The reliable way to copy course material to your laptop is the **Canvas REST API** with an access token from your own account — not a browser agent clicking through modules.

## Why not an agent?

A Playwright/LLM agent against `q.utoronto.ca` will fight session cookies, Duo, pagination, and file redirects to object storage. It will also miss items that never appear as a normal link (paginated Files, module items, pages). Canvas already exposes those as JSON:

- `GET /api/v1/courses`
- `GET /api/v1/courses/:id/files`
- `GET /api/v1/courses/:id/modules?include[]=items`
- `GET /api/v1/courses/:id/pages/:url`
- `GET /api/v1/courses/:id/assignments`
- `GET /api/v1/announcements?context_codes[]=course_:id`

This tool walks those endpoints, follows Canvas download redirects, and writes a folder tree you can grep, back up, or open offline.

## Where the code is

This repo is the whole app. The important files:

| File | What it does |
| --- | --- |
| `quercus_sync/canvas.py` | HTTP client for Canvas (`https://q.utoronto.ca/api/v1/...`) |
| `quercus_sync/sync.py` | Turns API JSON into a folder tree; skips date-locked courses |
| `quercus_sync/web.py` + `quercus_sync/static/` | Local UI on port 43147 |
| `quercus_sync/cli.py` | `quercus-sync courses` / `sync` / `serve` |
| `quercus_sync/mock.py` | Sample UTM term so you can try it without a token |

Run it from the repo root after `pip install -e .`.

## How the Canvas API works (and yes, students have it)

Quercus is Instructure Canvas. The website and the API are the same permission model.

1. You sign in at [q.utoronto.ca](https://q.utoronto.ca) (UTORid + Duo, same as always).
2. **Account → Settings → New Access Token**. That token is a student credential. You do not need a developer key, an instructor role, or ITS to “turn on the API.”
3. Every request sends `Authorization: Bearer <token>` to `/api/v1/...`.
4. Canvas answers with the courses, files, and pages **you** can already see. If a file is locked, unpublished, or the course is past its access date, the API returns 403 / `locked_for_user` / `access_restricted_by_date` — same as the site.

Useful student endpoints this tool calls:

```
GET /api/v1/users/self
GET /api/v1/courses?enrollment_state[]=active&enrollment_state[]=completed
GET /api/v1/courses/:id/files
GET /api/v1/courses/:id/modules?include[]=items
GET /api/v1/files/:id
GET /api/v1/courses/:id/pages/:url
GET /api/v1/courses/:id/assignments
GET /api/v1/announcements?context_codes[]=course_:id
```

Official reference: [Canvas LMS API](https://canvas.instructure.com/doc/api/). Treat the token like a password; it can act as you until you revoke it.

U of T still owns the files. This is a personal archive of material your enrolment already allows — not a way around locks, and not something to redistribute.

## What it downloads

From every course your token can still open (this term and concluded terms that Quercus has not date-locked):

- Course files (the Files tab), keeping folder names
- Files that only appear inside modules or as assignment attachments
- Module outlines
- Wiki pages
- Assignment descriptions
- Announcements
- Syllabus body

Optional: discussion threads.

It **does not** pull quiz questions, other students’ submissions, or files marked locked for you. Incremental runs skip files whose size already matches.

## Setup

Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Access token (real Quercus)

1. Sign in at [q.utoronto.ca](https://q.utoronto.ca).
2. **Account → Settings → New Access Token**.
3. Purpose: `Quercus Sync on my laptop`. Leave the expiry blank or set one.
4. Paste it in the web UI, or:

```bash
quercus-sync set-token
quercus-sync doctor
quercus-sync courses
quercus-sync sync
```

The token is stored in `data/config.json` on this machine. Do not commit it. Treat it like a password: it can act as you on Quercus.

### Demo campus

If you just want to see the layout, skip the token. The app ships a sample Fall UTM term (CSC148, MAT102, PSY100, ERS111) and will archive it into `downloads/`.

```bash
quercus-sync sync --demo
quercus-sync serve --host 127.0.0.1 --port 43147
```

## Web UI

```bash
python -m quercus_sync
```

Open [http://127.0.0.1:43147](http://127.0.0.1:43147). Save a token or stay on the demo campus, tick courses, archive. Files land under `downloads/{term}/{course}/`.

## Folder layout

```
downloads/
  Fall 2025/
    CSC148H5 F — Introduction to Computer Science/
      Files/Lectures/Week 01 — Python recap.pdf
      Modules/01 Week 1 — Getting oriented/module.md
      Pages/Welcome & how this course runs.html
      Assignments/Lab 2 — Recursion.html
      Announcements/2025-09-18 Lab rooms this Friday.html
      Syllabus.html
      _manifest.json
```

## St. George / other Canvas schools

Point the Canvas URL at your instance (`https://q.utoronto.ca` is the U of T default; some faculties still use an Instructure host). The API is the same.

## Limits and rules

- Personal study copy of courses **you** can already open. Do not redistribute lecture PDFs or publisher packs.
- U of T and your instructors still own the material; Quercus remains the source of truth for due dates and submissions.
- If an item is locked, unpublished, or embargoed until a date, this client cannot (and should not) bypass that.
- Rate limits: the client backs off on HTTP 429.

## Development

```bash
pytest
```
