#!/bin/sh
set -eu

# Docker creates a named-volume mount as root. Correct only that mount point at
# startup, then immediately drop privileges before running the API process.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/runtime/uploads
    mkdir -p /app/runtime/mesh
    chown 10001:10001 /app/runtime/uploads
    chown 10001:10001 /app/runtime/mesh
    exec setpriv --reuid=10001 --regid=10001 --init-groups "$@"
fi

exec "$@"
