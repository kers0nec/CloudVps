#!/usr/bin/env bash
# Start the Docker daemon that CloudVPS talks to, with the flags known to
# work in this (restricted) sandbox: no iptables binary available and the
# kernel has seccomp disabled, so networking features that need iptables and
# the default seccomp profile are switched off. Containers still get real
# CPU/memory limits and a real bridge IP (docker0, 172.17.0.0/16).
#
# If no dockerd binary is on PATH, see "Running the Docker daemon" in
# README.md for how the daemon in this environment was built from source.
set -euo pipefail

SOCKET=/var/run/docker.sock

if curl -sf --unix-socket "$SOCKET" http://localhost/_ping >/dev/null 2>&1; then
    echo "Docker daemon already reachable on $SOCKET"
    exit 0
fi

if ! command -v dockerd >/dev/null 2>&1; then
    echo "error: dockerd not found on PATH" >&2
    exit 1
fi

sudo dockerd \
    --host="unix://$SOCKET" \
    --storage-driver=overlay2 \
    --iptables=false \
    --ip6tables=false \
    --ip-forward=false \
    --ip-masq=false \
    --userland-proxy=false \
    --seccomp-profile=unconfined \
    --data-root=/var/lib/docker &

# Wait for the API socket to answer, then let non-root users connect.
for _ in $(seq 1 60); do
    if curl -sf --unix-socket "$SOCKET" http://localhost/_ping >/dev/null 2>&1; then
        sudo chmod 666 "$SOCKET"
        echo "Docker daemon is up on $SOCKET"
        exit 0
    fi
    sleep 1
done

echo "error: daemon did not come up within 60s; check dockerd logs" >&2
exit 1
