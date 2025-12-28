#!/usr/bin/env sh
set -eu

set -- action-server start \
    --address 0.0.0.0 \
    --port 8080 \
    --datadir=/action-server/datadir \
    --actions-sync=false \
    --min-processes 1 \
    --max-processes 3 \
    --reuse-processes \
    --full-openapi-spec

if [ -n "${ACTION_SERVER_API_KEY:-}" ] && [ "${ACTION_SERVER_API_KEY}" != "None" ]; then
    set -- "$@" --api-key "${ACTION_SERVER_API_KEY}"
else
    set -- "$@" --api-key None
fi

exec "$@"
