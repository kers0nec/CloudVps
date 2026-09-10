"""Real Docker-backed VPS engine for CloudVPS.

Each VPS is a *real* Docker container running an Ubuntu image. This module is
the authoritative source of truth for container state; the SQL database only
stores ownership metadata (user_id, container_id, plan, display name).

The Docker client is created lazily so the web app can still boot and serve
traffic (and report a clear error) on hosts where the Docker daemon is not
reachable, instead of crashing at import time.
"""

import os
import random
import string
import threading
import time
from urllib.parse import urlsplit, urlunsplit

# ---------------------------------------------------------------------------
# Plan catalogue. `cpu_shares`/`mem_limit` are applied to the container as real
# resource limits; `disk` is applied as a storage quota where the Docker
# storage driver supports it (retried without on hosts that don't).
# ---------------------------------------------------------------------------
PLANS = {
    'starter':     {'cpu': '0.5', 'memory': '512MB', 'storage': '10GB',
                    'cpu_shares': 512,  'mem_limit': '512m', 'disk': '10g'},
    'standard':    {'cpu': '1.0', 'memory': '1GB',   'storage': '20GB',
                    'cpu_shares': 1024, 'mem_limit': '1g',   'disk': '20g'},
    'performance': {'cpu': '2.0', 'memory': '2GB',   'storage': '40GB',
                    'cpu_shares': 2048, 'mem_limit': '2g',   'disk': '40g'},
}

VPS_IMAGE = 'ubuntu:22.04'

_client = None
_client_lock = threading.Lock()


class DockerUnavailableError(RuntimeError):
    """Raised when the Docker SDK cannot reach a daemon.

    ``docker.from_env()`` performs API-version negotiation while constructing
    the client.  That means a missing socket can raise before the caller ever
    gets a client to ping (the common error is ``Error while fetching server
    API version``).  Keeping this as a distinct error lets the HTTP layer
    return a useful 503 instead of leaking an opaque SDK traceback.
    """

    def __init__(self, cause):
        self.cause = cause
        self.endpoint = docker_endpoint()
        super().__init__(_connection_message(self.endpoint, cause))


def docker_endpoint():
    """Return the configured Docker endpoint without exposing credentials."""
    raw = (os.environ.get('DOCKER_HOST') or '').strip()
    if not raw:
        return 'unix:///var/run/docker.sock'

    # DOCKER_HOST may contain credentials for a TCP/SSH endpoint.  Keep the
    # diagnostic useful while ensuring those credentials never reach an API
    # response or the browser.
    try:
        parsed = urlsplit(raw)
        if parsed.username or parsed.password:
            host = parsed.hostname or ''
            if parsed.port:
                host = f'{host}:{parsed.port}'
            netloc = f'***:***@{host}'
            return urlunsplit((parsed.scheme, netloc, parsed.path,
                               parsed.query, parsed.fragment))
    except ValueError:
        # A malformed port can make ``parsed.port`` raise.  Do not fall back
        # to the raw value here because it may contain a password.
        scheme = raw.split('://', 1)[0] if '://' in raw else 'docker'
        return f'{scheme}://<redacted>'
    return raw[:200]


def _connection_message(endpoint, cause):
    """Build an actionable, safe message for a failed Docker connection."""
    detail = str(cause) or cause.__class__.__name__
    lowered = detail.lower()
    if isinstance(cause, ModuleNotFoundError) and getattr(cause, 'name', '') == 'docker':
        return (
            'Docker is not available: the Docker SDK is not installed. '
            'Install requirements.txt before starting the backend.'
        )
    if isinstance(cause, FileNotFoundError) or 'filenotfounderror' in lowered:
        return (
            f'Docker is not available: no daemon socket was found at {endpoint}. '
            'Start the Docker daemon or set DOCKER_HOST to a reachable daemon. '
            f'({detail})'
        )
    if 'permission denied' in lowered:
        return (
            f'Docker is not available: permission was denied for {endpoint}. '
            'Add the backend user to the Docker group or grant access to the '
            f'socket. ({detail})'
        )
    if 'connection refused' in lowered or 'cannot connect' in lowered:
        return (
            f'Docker is not available: the daemon at {endpoint} refused the '
            f'connection. Start the daemon and try again. ({detail})'
        )
    return f'Docker is not available at {endpoint}: {detail}'


def _close_client(client):
    """Close a partially-created client without masking the original error."""
    if client is None:
        return
    try:
        client.close()
    except Exception:  # noqa: BLE001 - cleanup must never mask the cause
        pass


def _connect():
    """Create and validate a Docker client, translating setup failures."""
    client = None
    try:
        import docker
        # ``from_env`` may negotiate the API version before returning, so both
        # construction and ping must be inside this try block.
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 - SDK has several error classes
        _close_client(client)
        raise DockerUnavailableError(exc) from exc


def get_client():
    """Return a validated, cached Docker client, connecting on first use.

    A failed connection never leaves a half-initialised client behind.  A
    cached client is pinged before reuse as well, so stopping the daemon and
    starting it again self-heals on the next request instead of leaving the
    process stuck with a dead SDK client.
    """
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.ping()
            except Exception as exc:  # noqa: BLE001 - daemon may have stopped
                stale = _client
                _client = None
                _close_client(stale)
                raise DockerUnavailableError(exc) from exc
        if _client is None:
            _client = _connect()
        return _client


def generate_container_suffix():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _ip_of(container):
    """Best-effort extraction of the container's bridge IP address."""
    nets = (container.attrs.get('NetworkSettings') or {}).get('Networks') or {}
    for cfg in nets.values():
        ip = (cfg or {}).get('IPAddress')
        if ip:
            return ip
    return (container.attrs.get('NetworkSettings') or {}).get('IPAddress') or 'N/A'


def _host_kwargs(config, with_disk=True):
    """Resource limits for the container's HostConfig.

    ``containers.create()`` on docker-py >= 4 builds the HostConfig from
    individual keyword arguments (cpu_shares/mem_limit/storage_opt); passing
    a pre-built ``host_config=`` object is rejected with a TypeError.
    """
    kwargs = {'cpu_shares': config['cpu_shares'], 'mem_limit': config['mem_limit']}
    if with_disk:
        kwargs['storage_opt'] = {'size': config['disk']}
    return kwargs


def create_vps_container(user_id, plan='starter'):
    """Provision a real VPS container for `user_id`. Returns a dict with the
    real container id, status, plan specs and assigned IP address."""
    config = PLANS.get(plan, PLANS['starter'])
    client = get_client()
    container_name = f"vps-{user_id}-{generate_container_suffix()}"
    labels = {'app': 'cloudvps', 'user_id': str(user_id), 'plan': plan}

    def _create(with_disk=True):
        return client.containers.create(
            image=VPS_IMAGE,
            name=container_name,
            command='sleep infinity',
            hostname=container_name,
            labels=labels,
            **_host_kwargs(config, with_disk),
        )

    try:
        container = _create(with_disk=True)
    except Exception as exc:  # noqa: BLE001 - translate to a clear error
        msg = str(exc)
        if 'not found' in msg.lower() or 'no such image' in msg.lower():
            # Pull the base image on demand, then retry.
            client.images.pull(VPS_IMAGE)
            container = _create(with_disk=True)
        elif 'storage' in msg.lower():
            # Disk quota unsupported on this host's storage driver — bring the
            # VPS up with CPU/RAM limits only.
            container = _create(with_disk=False)
        else:
            raise

    container.start()

    # Give the network stack a moment to assign the bridge IP, then sync state.
    deadline = time.time() + 5
    while True:
        container.reload()
        if _ip_of(container) not in (None, 'N/A', '') or time.time() >= deadline:
            break
        time.sleep(0.25)
    return {
        'container_id': container.id,
        'name': container.name,
        'status': container.status,
        'plan': plan,
        'cpu': config['cpu'],
        'memory': config['memory'],
        'storage': config['storage'],
        'ip': _ip_of(container),
    }


def get_container(container_id):
    return get_client().containers.get(container_id)


def describe(container):
    """Build a state snapshot of a container (real status + IP)."""
    container.reload()
    return {
        'container_id': container.id,
        'name': container.name,
        'status': container.status,
        'plan': (container.labels or {}).get('plan', 'starter'),
        'ip': _ip_of(container),
    }


def start_container(container_id):
    client = get_client()
    container = client.containers.get(container_id)
    container.start()
    container.reload()
    return container.status


def stop_container(container_id):
    client = get_client()
    container = client.containers.get(container_id)
    container.stop()
    container.reload()
    return container.status


def delete_container(container_id):
    client = get_client()
    container = client.containers.get(container_id)
    container.remove(force=True)
    return True
