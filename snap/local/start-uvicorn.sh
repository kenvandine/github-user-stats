#!/bin/sh
set -e

ALLOWED_USERS="$(snapctl get allowed-users)"
if [ -n "$ALLOWED_USERS" ]; then
    export ALLOWED_USERS
fi

GITHUB_TOKEN="$(snapctl get github-token)"
if [ -n "$GITHUB_TOKEN" ]; then
    export GITHUB_TOKEN
fi

export PYTHONPATH="$SNAP"

exec "$SNAP/bin/python3" -m uvicorn app.main:app --host 127.0.0.1 --port 8009
