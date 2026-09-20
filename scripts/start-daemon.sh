#!/usr/bin/env sh
set -eu
: "${JEV_APPROVAL_CONFIG:?Set the absolute path to the service TOML}"
: "${JEV_APPROVAL_TOKEN:?Set a random shared token of at least 32 characters}"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 -I "$ROOT/scripts/launcher.py" serve --config "$JEV_APPROVAL_CONFIG"
