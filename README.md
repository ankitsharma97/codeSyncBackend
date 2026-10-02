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
| `SQLITE_PATH` | `db.sqlite3` | SQLite file location |
| `GIT_PROXY_HOSTS` | `github.com,gitlab.com,bitbucket.org` | Hosts the proxy may contact |
| `GIT_PROXY_ORIGINS` | `*` | CORS origin allowed to use the proxy — set to your frontend URL |

## Deploy

- Build: `pip install -r requirements.txt && python manage.py migrate`
- Start: `uvicorn codeSync.asgi:application --host 0.0.0.0 --port $PORT`
- Use a persistent database (e.g. Postgres) — ephemeral disks lose saved rooms.

## Layout

| File | What it is |
|---|---|
| `main/consumers.py` | WebSocket consumer (the sync protocol) |
| `main/rooms.py` | Per-process room registry, debounced saving, locking |
| `main/awareness.py` | Presence message encoding |
| `main/gitproxy.py` | Allow-listed, rate-limited git-over-HTTPS relay |
| `main/models.py` | `RoomDocument` (compressed snapshot) |

Full architecture, design decisions and trade-offs: see **`project.md`** in the main project folder.
