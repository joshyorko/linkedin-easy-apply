#!/usr/bin/env sh
set -eu

set -- action-server start \
    --address 0.0.0.0 \
    --port 8080 \
    --datadir=/action-server/datadir \
    --actions-sync=false \
    --min-processes 1 \
    --max-processes 3 \
    --reuse-processes
if [ -n "${ACTION_SERVER_API_KEY:-}" ] && [ "${ACTION_SERVER_API_KEY}" != "None" ]; then
    set -- "$@" --api-key "${ACTION_SERVER_API_KEY}"
fi

# If SERVER_URL is provided via environment, set it so the OpenAPI 'servers' section
# reflects the external/public URL (useful when behind a tunnel or reverse proxy).
if [ -n "${SERVER_URL:-}" ]; then
    set -- "$@" --server-url "${SERVER_URL}"
fi

exec "$@"
