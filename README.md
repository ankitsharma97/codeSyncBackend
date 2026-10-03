# CodeWithFriend

**A real-time collaborative code editor for pair programming, interviews and teaching.** Share a link, edit the same files together with live cursors, run Python and JavaScript right in the browser, and use a built-in terminal with a shared `git` repository — no sign-up, nothing to install.

![A room with two people editing the same file](docs/images/room.png)

> **Want the full story?** [`project.md`](project.md) explains every concept, design decision and trade-off in this project in depth.

---

## Features

**Collaboration**
- **Conflict-free live editing** — built on [Yjs](https://yjs.dev) (a CRDT), so simultaneous edits always merge cleanly, even after a network drop.
- **Live cursors and presence** — see who is in the room and where they are typing; colours and names are consistent everywhere.
- **Rooms that persist** — the server stores each room (compressed), so the code is still there after everyone leaves.
- **No accounts** — create a room, copy the invite link, done.

**Projects, not snippets**
- **Files and folders** — a full file explorer with create / rename / delete / drag-to-move, synced live.
- **Import from your computer** — drop files or a whole folder (skips `node_modules`, `.git`, binaries; enforces size limits).
- **Tabs, 10+ languages** — syntax highlighting for JavaScript, TypeScript, Python, Java, C/C++, HTML, CSS, JSON, SQL and Markdown.
- **Live previews** — HTML (inlines the `.css` and `.js` files it references) and Markdown (sanitized).

**Run code safely**
- **Python and JavaScript in the browser** — executed in locked-down Web Workers (Python through [Pyodide](https://pyodide.org)/WebAssembly). Untrusted code never runs on the server.
- **Multi-file aware** — Python files can `import` each other; JavaScript files can `require('./x.js')`.
- **Shared output** — everyone in the room sees the result of a run.

**A terminal with git**

![The in-browser terminal running git](docs/images/terminal-git.png)

- A shell built for the project: `ls`, `cd`, `cat`, `grep`, pipes, redirects, globs, tab completion, history, `python`, `node`, and more.
- **Real git, shared by the room** — `init`, `add`, `commit`, `diff`, `log`, `branch`, `checkout`, `merge`, `reset`, `tag`, … One repository per room; everyone's commits show up for everyone, with the right author.
- **GitHub / GitLab / Bitbucket** — `clone`, `fetch`, `pull`, `push` over HTTPS through a locked-down backend relay.
- **Built-in guide** — a Help button (or `docs` in the terminal) opens a how-to for everything above.

| Live preview | Guide | Phone |
|---|---|---|
| ![HTML preview built from three files](docs/images/preview.png) | ![The in-app guide](docs/images/guide.png) | ![The phone layout](docs/images/mobile.png) |

---

## How it works (the 60-second version)

```mermaid
flowchart LR
    subgraph Browser
        UI["React UI<br/>CodeMirror · Explorer · Terminal"]
        YD[("Yjs document<br/>files · text · git data · run output")]
        W["Web Workers<br/>JavaScript · Pyodide"]
        G["isomorphic-git<br/>runs in the browser"]
    end
    UI <--> YD
    UI --> W
    G <--> YD
    YD <-->|"WebSocket<br/>y-websocket protocol"| C["Django Channels consumer"]
    C <--> R[("Room registry<br/>one Yjs doc per room")]
    R -->|"debounced, zlib-compressed"| DB[("Database<br/>SQLite / Postgres")]
    C <-->|"channel layer"| X["Other server processes<br/>via Redis"]
    G -->|"HTTPS via /git-proxy"| P["Git proxy<br/>allow-listed hosts only"]
    P --> GH[("GitHub · GitLab · Bitbucket")]
```

- The **whole project lives in one Yjs document**: the file tree, every file's text, the git repository's internal files, and the last run's output. Syncing the document syncs everything.
- The **server is a relay with memory.** It keeps a copy of each room's document so late joiners get the full state, and saves it to the database.
- **Code, git and the terminal all run in the browser.** The only server-side extras are the WebSocket relay and a small, strictly allow-listed git proxy (browsers can't reach GitHub directly).

---

## Tech stack

| Layer | Technology |
|---|---|
| Real-time sync | [Yjs](https://yjs.dev) (CRDT), `y-websocket` protocol, `y-codemirror.next` |
| Backend | Django 4.2, Django Channels 4 (ASGI), Uvicorn, [pycrdt](https://github.com/jupyter-server/pycrdt) |
| Scaling | `channels-redis` channel layer (optional; in-memory for development) |
| Storage | SQLite for development, Postgres in production (`DATABASE_URL`); zlib-compressed room snapshots |
| Frontend | React 18 (Create React App), CodeMirror 6, React Router |
| In-browser execution | Web Workers, [Pyodide](https://pyodide.org) (Python → WebAssembly) |
| Terminal and git | [xterm.js](https://xtermjs.org), [isomorphic-git](https://isomorphic-git.org), [jsdiff](https://github.com/kpdecker/jsdiff) |
| Previews | `marked` + DOMPurify, sandboxed `<iframe>` |

---

## Quick start

You need **Python 3.9+** and **Node 24** (`nvm use` picks it up from `.nvmrc`). Run the backend and frontend in two terminals.

### 1. Backend

```bash
cd codeSyncBackend
python -m venv env && source env/bin/activate      # Windows: env\Scripts\activate
pip install -r requirements-dev.txt                # requirements.txt is enough if you won't run tests
python manage.py migrate
uvicorn codeSync.asgi:application --reload --port 8000
```

> Use `uvicorn`, **not** `python manage.py runserver` — `runserver` doesn't serve WebSockets here.
> Check it's alive: <http://localhost:8000/health> → `ok`.

### 2. Frontend

```bash
cd codeSyncFrontend
npm install
npm start                                          # http://localhost:3000
```

In development the frontend connects to `ws://localhost:8000/ws/code_sync`. Open the app in two browser windows, join the same room, and edit.

### 3. Run the tests

```bash
cd codeSyncBackend
python manage.py test        # 12 tests: sync, persistence, awareness, git proxy security
```

---

## Configuration

**Backend** — environment variables (all optional in development):

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | insecure dev key | Django secret. **Set this in production.** |
| `DEBUG` | `true` | Set `false` in production. |
| `ALLOWED_HOSTS` | `*` | Comma-separated hostnames. |
| `WS_ALLOWED_ORIGINS` | `*` | Origins allowed to open a WebSocket, e.g. `https://app.example.com`. |
| `REDIS_URL` | *(unset)* | Enables the Redis channel layer for multiple server processes. |
| `DATABASE_URL` | *(unset)* | Postgres connection string, e.g. `postgres://user:pass@host:5432/db`. When unset, SQLite is used. |
| `SQLITE_PATH` | `db.sqlite3` | Where the SQLite file lives (used only when `DATABASE_URL` is unset). |
| `GIT_PROXY_HOSTS` | `github.com,gitlab.com,bitbucket.org` | Hosts the git proxy may contact. |
| `GIT_PROXY_ORIGINS` | `*` | CORS origin allowed to use the git proxy. **Set to your frontend URL in production.** |

**Frontend** — `REACT_APP_WS_URL` is the base WebSocket URL (default `ws://localhost:8000/ws/code_sync`). `.env.production` sets the production value; the git proxy URL is derived from it.

---

## Deploying

The project is set up for [Render](https://render.com), but any host that runs an ASGI server will do.

- **Backend (web service)**
  - Build: `pip install -r requirements.txt && python manage.py migrate`
  - Start: `uvicorn codeSync.asgi:application --host 0.0.0.0 --port $PORT`
  - Set `SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS`, `WS_ALLOWED_ORIGINS`, `GIT_PROXY_ORIGINS`.
  - Set `DATABASE_URL` to a Postgres database — free-tier disks are wiped on redeploy, which would lose saved rooms. A step-by-step walkthrough is in [`codeSyncBackend/README.md`](codeSyncBackend/README.md#deploy-to-render).
  - Running more than one process? Set `REDIS_URL`.
- **Frontend (static site)**
  - Build: `npm install && npm run build`, publish `build/`.
  - Add a rewrite rule `/*` → `/index.html` so deep links such as `/editor/<room>` and `/docs` work.

> **Why Uvicorn?** It negotiates WebSocket compression (`permessage-deflate`), which Daphne doesn't. On real project data this cut sync traffic to roughly 30% of its size.

---

## Project structure

```text
code_with_friend/
├── README.md              ← you are here
├── project.md             ← the deep-dive: concepts, decisions, trade-offs
├── docs/images/           ← screenshots used in this README
├── codeSyncBackend/       ← Django + Channels (its own git repo)
│   ├── codeSync/          settings, urls, asgi entrypoint
│   └── main/
│       ├── consumers.py   WebSocket consumer: the y-websocket protocol
│       ├── rooms.py       per-room server document, saving, locking
│       ├── awareness.py   presence (cursor/user) message codec
│       ├── gitproxy.py    allow-listed git-over-HTTPS relay
│       ├── models.py      RoomDocument (compressed snapshot)
│       └── tests.py
└── codeSyncFrontend/      ← React app (its own git repo)
    └── src/
        ├── pages/         Home, EditorPage (the room), Editor, DocsPage
        ├── components/    Explorer, Tabs, OutputPanel, TerminalPanel, Avatars, Docs
        ├── hooks/         useCollab — joins a room and exposes its state
        ├── runner/        sandboxed JS / Python execution
        ├── terminal/      shell, line editor, git, the project filesystem
        ├── utils/         file tree logic, importing, HTML bundling, Markdown
        └── docs/          the in-app guide's content
```

---

## Security model

| Concern | How it is handled |
|---|---|
| Untrusted code | Runs only in browser Web Workers with network APIs removed and an 8-second timeout; never on the server. |
| Preview content | HTML previews run in an `<iframe sandbox="allow-scripts">` with no access to the app; Markdown is sanitized with DOMPurify and gets no scripts at all. |
| Git proxy abuse | Exact-match host allow-list, git endpoints only, method checks, no server-side redirect following, size caps, rate limiting; tests cover each rejection. |
| Credentials | A GitHub token is stored only in the user's browser (never in the shared room) and passed through as a standard auth header. |
| Oversized / malformed input | WebSocket messages are capped (2 MB); corrupt updates close the socket instead of crashing the server. |

**Not included:** user accounts or private rooms — anyone with a room link has full access. That's by design for a no-sign-up tool; see [Limitations](#limitations).

---

## Limitations

- **No authentication.** Treat a room link like a password.
- **Size limits.** A project holds up to 100 files and folders; a stored git history is capped at 12 MB. Large repositories won't fit.
- **JavaScript** supports `require`, not ES `import`. **Python** can't install packages (no `pip`).
- **Git:** no `stash`, `rebase` or `cherry-pick`; a merge with conflicts stops and changes nothing; two people running git commands at the exact same moment can collide.
- **Not a full Linux terminal** — no `npm`, `curl`, `sudo`, or editors like `vim`.
- Backend is tested; the frontend relies on manual browser testing (see [`project.md`](project.md#17-testing)).

## Ideas for next steps

Accounts and private rooms · incremental database saves instead of whole-document snapshots · Playwright end-to-end tests · version history / time travel UI · more run languages via a server-side sandbox · an LSP-style language server for completions.

---

## Learn more

- [`project.md`](project.md) — how and why everything is built the way it is (CRDTs, WebSockets, the sandbox, the git filesystem, the proxy, the decision log, bugs found and lessons learned, and interview-style Q&A).
- The **in-app guide** — click the `?` button in any room, or visit `/docs`.

Built by [Ankit Sharma](https://github.com/ankitsharma97).
