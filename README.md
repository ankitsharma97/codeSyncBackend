# CodeWithFriend — backend

Django + Django Channels (ASGI) service for [CodeWithFriend](https://github.com/ankitsharma97), a real-time collaborative code editor.

It does four things:

1. **Relays** the [y-websocket](https://github.com/yjs/y-websocket) protocol between everyone in a room (`ws/code_sync/<room>`).
2. **Remembers** each room as a server-side [Yjs](https://yjs.dev) document (via `pycrdt`), so late joiners get the full state.
3. **Saves** rooms to the database (debounced, zlib-compressed snapshots).
4. **Proxies git** over HTTPS (`/git-proxy/…`) to GitHub/GitLab/Bitbucket so the in-browser terminal can clone and push — strictly allow-listed.

No user code ever runs here: code execution, git and the terminal all happen in the browser.

## Run it

```bash
python -m venv env && source env/bin/activate
pip install -r requirements-dev.txt        # requirements.txt is enough if you won't run tests
python manage.py migrate
uvicorn codeSync.asgi:application --reload --port 8000
```

Use `uvicorn`, not `manage.py runserver` (which doesn't serve WebSockets here). Health check: <http://localhost:8000/health>.

## Test

```bash
python manage.py test      # 12 tests: sync, persistence, presence, backward compatibility, git-proxy security
```

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | insecure dev key | Django secret — **set in production** |
| `DEBUG` | `true` | Set `false` in production |
| `ALLOWED_HOSTS` | `*` | Comma-separated hostnames |
| `WS_ALLOWED_ORIGINS` | `*` | Origins allowed to open WebSockets |
| `REDIS_URL` | unset | Redis channel layer for multiple processes |
| `DATABASE_URL` | unset | Postgres connection string (`postgres://user:pass@host:5432/db`). Unset → SQLite |
| `SQLITE_PATH` | `db.sqlite3` | SQLite file location (only when `DATABASE_URL` is unset) |
| `GIT_PROXY_HOSTS` | `github.com,gitlab.com,bitbucket.org` | Hosts the proxy may contact |
| `GIT_PROXY_ORIGINS` | `*` | CORS origin allowed to use the proxy — set to your frontend URL |

## Deploy to Render

Render hosts both a Python web service (WebSockets are supported) and Postgres. You need a GitHub repo with this code pushed.

**1. Create a Postgres database** — Render dashboard → **New +** → **PostgreSQL**. Pick a name (e.g. `codesync-db`) and the **same region** you'll use for the web service. After it's created, copy its **Internal Database URL**.

> A database on a free plan may expire or be limited — check Render's current pricing. Saved rooms live in this database, so use a paid plan for anything you want to keep.

**2. Create the web service** — **New +** → **Web Service** → connect this repository, then set:

| Setting | Value |
|---|---|
| Name | `codesyncbackend` (the production frontend is already configured for `https://codesyncbackend.onrender.com`; use another name if you change `REACT_APP_WS_URL` too) |
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt && python manage.py migrate` |
| Start command | `uvicorn codeSync.asgi:application --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Instance type | Free works for demos (it sleeps when idle); a paid instance stays awake |

**3. Environment variables** (the service's *Environment* tab):

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `SECRET_KEY` | a long random string — generate one with `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | `codesyncbackend.onrender.com` (your service's hostname, no `https://`) |
| `DATABASE_URL` | the Internal Database URL from step 1 |
| `WS_ALLOWED_ORIGINS` | your frontend's exact origin, e.g. `https://codewithfriend.onrender.com` (comma-separate several; no trailing slash) |
| `GIT_PROXY_ORIGINS` | the same frontend origin |

Leave `REDIS_URL` unset while you run a **single instance**. Don't scale to several instances without adding Redis and setting `REDIS_URL`.

**4. Deploy and check.** Watch the logs for `Applying main.0004_roomdocument_compressed... OK` (the migrations) and `Uvicorn running on http://0.0.0.0:…`. Then open `https://<your-service>.onrender.com/health` — it should say `ok`.

**5. Point the frontend at it.** Set `REACT_APP_WS_URL=wss://<your-service>.onrender.com/ws/code_sync` (it's in `.env.production`), rebuild and redeploy the static site, open the app in two browsers, join one room, and edit.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Health check fails / `DisallowedHost` | `ALLOWED_HOSTS` doesn't include your service hostname |
| Browser shows the WebSocket failing immediately (403) | `WS_ALLOWED_ORIGINS` must match the frontend origin exactly (scheme + host, no trailing slash) |
| `git clone` in the terminal says it can't reach the proxy | `GIT_PROXY_ORIGINS` is missing or wrong |
| `no such table: main_roomdocument` | Migrations didn't run — check the build command |
| Rooms disappear after each deploy | `DATABASE_URL` isn't set, so SQLite on the ephemeral disk is being used |
| First load after a quiet period takes 30–60 s | Free instances sleep when idle. Open WebSockets drop at that point; the app reconnects on its own |
| Build fails installing packages | Set `PYTHON_VERSION` (3.12.x is a safe choice) |

## Layout

| File | What it is |
|---|---|
| `main/consumers.py` | WebSocket consumer (the sync protocol) |
| `main/rooms.py` | Per-process room registry, debounced saving, locking |
| `main/awareness.py` | Presence message encoding |
| `main/gitproxy.py` | Allow-listed, rate-limited git-over-HTTPS relay |
| `main/models.py` | `RoomDocument` (compressed snapshot) |

Full architecture, design decisions and trade-offs: see **`project.md`** in the main project folder.
