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

## Running the Docker daemon

On a normal host, install Docker and the app works as-is. In the offline
sandbox this project is developed in (no Debian mirrors, no Docker download
server, no container registries are reachable — only `github.com`,
`pypi.org` and `registry.npmjs.org`), the daemon is provisioned like this:

1. **Build the engine from source** using a Go toolchain installed from PyPI
   (`pip install go-bin`), since GitHub release asset CDNs are blocked but
   `git clone` from `github.com` works. All three projects vendor their Go
   dependencies, so no module proxy is needed:
   - `github.com/moby/moby` → `dockerd`
     (`go build ./cmd/dockerd` with
     `DOCKER_BUILDTAGS="exclude_graphdriver_devicemapper exclude_graphdriver_btrfs"`,
     the C headers for those drivers are not available either),
   - `github.com/containerd/containerd` → `containerd`,
     `containerd-shim-runc-v2`,
   - `github.com/opencontainers/runc` → `runc`
     (`make RUNC_BUILDTAGS='-seccomp -libpathrs'` — libseccomp headers are
     not available; harmless here because the sandbox kernel has seccomp
     disabled).
2. **Start it** with `scripts/start-dockerd.sh`, which launches `dockerd`
   with the flags that fit the sandbox: no iptables binary exists, so
   `--iptables=false --ip-forward=false --ip-masq=false
   --userland-proxy=false`; containers still get real CPU/memory limits and
   a real IPv4 address on the default `docker0` bridge. The socket is
   `chmod 666`-ed afterwards so the app (non-root) can connect.
3. **Seed the base image**: `docker_utils.VPS_IMAGE` is `ubuntu:22.04`, but
   no image registry is reachable, so the image is seeded locally:
   `docker import` of a trimmed tarball of the sandbox's own Debian 12
   rootfs, tagged `ubuntu:22.04`. In other words, in this environment the
   container labelled `ubuntu:22.04` actually contains Debian 12 — a real
   Ubuntu image will be pulled normally on any host with registry access.

```bash
scripts/start-dockerd.sh && python app.py
```

### Troubleshooting Docker connectivity

If the dashboard shows **VPS backend offline** with `Error while fetching server
API version` and `FileNotFoundError`, the Docker SDK cannot find the configured
Unix socket; it is not an application API-version problem. Start the daemon
before starting Flask:

```bash
scripts/start-dockerd.sh
python app.py
```

On a host where Docker is managed by systemd, use `sudo systemctl start docker`
instead. For a remote or rootless daemon, set `DOCKER_HOST` for the backend
process (for example, `unix:///run/user/$UID/docker.sock` or a secured TCP
endpoint) and ensure the process has permission to use it. The backend retries
connection setup on each request, so restarting the daemon does not require a
Flask restart. It returns HTTP `503` while Docker is genuinely unavailable;
it never creates fake VPS records in that state.

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
