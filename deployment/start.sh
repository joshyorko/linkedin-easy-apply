#!/usr/bin/env sh
set -eu

key_file=${ACTION_SERVER_API_KEY_FILE:-/run/secrets/runtime-api-key}
if [ ! -s "$key_file" ] || [ ! -r "$key_file" ]; then
    echo 'A readable, nonempty runtime API-key file is required' >&2
    exit 1
fi
key=$(cat "$key_file")
if [ -z "$key" ] || [ "$key" = None ]; then
    echo 'Runtime authentication must not be disabled' >&2
    exit 1
fi

exec action-server start \
    --address 127.0.0.1 \
    --port "${ACTION_SERVER_PORT:-8080}" \
    --dir /opt/application \
    --datadir /var/lib/easy-apply/datadir \
    --actions-sync=true \
    --min-processes 1 --max-processes 1 \
    --api-key "$key"
