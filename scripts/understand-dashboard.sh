#!/bin/sh
# Use the runtime already pinned and built in the image, never npx/downloads.
set -eu

project=$(CDPATH='' cd -- "${1:-.}" && pwd -P)
if [ "$#" -gt 0 ]; then shift; fi

# Match upstream: the legacy directory takes precedence when it exists.
if [ -f "$project/.understand-anything/knowledge-graph.json" ]; then
    data="$project/.understand-anything"
else
    data="$project/.ua"
fi
if [ ! -f "$data/knowledge-graph.json" ]; then
    echo "No knowledge graph found: $data/knowledge-graph.json" >&2
    echo "Analyze this project with /understand first; this command only views existing graphs." >&2
    exit 1
fi

plugin=${UNDERSTAND_ANYTHING_ROOT:-/opt/understand-anything/understand-anything-plugin}
dashboard="$plugin/packages/dashboard"
if [ ! -x "$dashboard/node_modules/.bin/vite" ]; then
    echo "Understand Anything dashboard is not installed in $plugin. Rebuild/pull the devenv image." >&2
    exit 1
fi

# Allow the known tailnet hostname without disabling Vite's Host checks.
# Keep an explicit caller override for other hosts (localhost/IPs work in Vite).
export __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS="${__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS:-calculation.tailnet.internal}"
export GRAPH_DIR="$project" BROWSER=none
echo "Viewing: $data/knowledge-graph.json"
echo "Open the Dashboard URL printed below (including ?token=). Stop with Ctrl+C."
cd "$dashboard"
# Podman forwards published ports to the container interface, not its loopback.
# Publication on the host is still controlled by Compose/just (loopback or tailnet).
# Caller flags come last so an explicit --host/--port overrides these defaults.
exec ./node_modules/.bin/vite --strictPort --host 0.0.0.0 --port 5173 "$@"
