# CloudVPS

A real, Docker-backed VPS control panel. Each "VPS" you create is an actual
Docker container (Ubuntu) provisioned with real CPU, memory and disk limits,
a real container ID and a real IP address. There is no fake/placeholder data —
the web app records ownership metadata and the Docker daemon is the source of
truth for container state.

## Features
- User registration / login with hashed passwords (Werkzeug `pbkdf2:sha256`).
- API-key authenticated REST API.
- Create / start / stop / delete real VPS containers.
- Live status and IP synced from the Docker daemon on every list request;
  rows whose container no longer exists are pruned automatically.
- `/api/health` reports live Docker reachability (with the backend error
  detail), and the dashboard shows a banner whenever the daemon is offline.
- Plan catalogue served by `/api/plans` — the dashboard renders it dynamically,
  so there is a single source of truth for plans.
- Single-page dashboard (`index.html`) served by the same app.

## Requirements
- Python 3.10+
- A working Docker daemon that this app can reach (`DOCKER_HOST`, or the
  default local socket). Without Docker, the API boots and serves the UI but
  returns a clear `503` (including the backend error detail) when a VPS
  operation is attempted.
- `docker-py >= 7.1.0` (pinned in `requirements.txt`); 7.0.0 is incompatible
  with modern `requests` and fails with "Not supported URL scheme http+docker".

## Install
```bash
pip install -r requirements.txt
```

## Run
```bash
python app.py          # listens on :5000 (override with PORT env var)
```
Then open <http://localhost:5000>.

## API
| Method | Path                      | Auth | Description                |
|--------|---------------------------|------|----------------------------|
| POST   | `/api/register`           | —    | Create account             |
| POST   | `/api/login`              | —    | Get API key                |
| GET    | `/api/plans`              | —    | List plans                |
| POST   | `/api/vps`                | key  | Create (provision) a VPS  |
| GET    | `/api/vps`                | key  | List your VPS instances   |
| GET    | `/api/vps/<id>`           | key  | Get one VPS               |
| POST   | `/api/vps/<id>/start`     | key  | Start the container       |
| POST   | `/api/vps/<id>/stop`      | key  | Stop the container        |
| DELETE | `/api/vps/<id>`           | key  | Delete the container      |
| GET    | `/api/user`               | key  | Current user + VPS count  |
| GET    | `/api/health`             | —    | Service + Docker status   |

Pass the API key as the `X-API-Key` header.
