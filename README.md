# Splendor Prototype

This repo now has two delivery paths:

- a legacy PySide6 desktop prototype for LAN play
- a new hosted web stack for browser-first multiplayer

The shared source of truth is the Python rules engine in `splendor_core`.

## Web-First Local Dev

### 1. Install the Python API dependencies

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[web]"
```

### 2. Start the hosted game API

```bash
. .venv/bin/activate
splendor-web-api
```

By default the API runs on `http://127.0.0.1:8000`.

Environment variables:

- `SPLENDOR_WEB_HOST`
- `SPLENDOR_WEB_PORT`
- `SPLENDOR_WEB_RELOAD=1`
- `SPLENDOR_WEB_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`

### 3. Start the React/Vite web client

```bash
cd web
npm install
cp .env.example .env
npm run dev
```

The web client defaults to `http://127.0.0.1:8000` as its API base.

## Web App Features In This Repo

- Create room and join room flow
- Room code and share-link invite flow
- WebSocket-driven game state sync
- Browser storage for reconnect after refresh
- Mobile-friendly responsive layout
- Basic PWA manifest + service worker wiring for installability

## Desktop Prototype

The desktop client still exists as a fallback and reference implementation.

Run from source:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
splendor-desktop
```

## Desktop Packaging

Install the project plus the build dependency:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[build]"
```

macOS:

```bash
./scripts/build_macos.sh
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -e ".[build]"
.\scripts\build_windows.ps1
```

These builds are unsigned and still use the original LAN discovery / TCP flow.

## Tests

Run the Python suite:

```bash
python3 -m unittest discover -s tests -v
```

If FastAPI test dependencies are not installed, the API integration tests are skipped automatically while the core and room-manager tests still run.
