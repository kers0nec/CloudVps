"""Real Docker-backed VPS engine for CloudVPS.

Each VPS is a *real* Docker container running an Ubuntu image. This module is
the authoritative source of truth for container state; the SQL database only
stores ownership metadata (user_id, container_id, plan, display name).

The Docker client is created lazily so the web app can still boot and serve
traffic (and report a clear error) on hosts where the Docker daemon is not
reachable, instead of crashing at import time.
"""

import random
import string
import time

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


def get_client():
    """Return a cached Docker client, connecting on first use.

    A failed connection never leaves a half-initialised client behind, so the
    next call retries cleanly once the daemon is reachable.
    """
    global _client
    if _client is None:
        import docker
        client = docker.from_env()
        try:
            client.ping()
        except Exception as exc:  # docker not running / not installed
            client.close()
            raise RuntimeError(f"Docker is not available: {exc}")
        _client = client
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
