#!/bin/sh
# Claude Code спрашивает о доверии к каждой новой папке. Контейнер видит только
# смонтированный проект, поэтому рабочая папка помечается доверенной сразу
python3 - <<'EOF'
import json, os

path = os.path.expanduser("~/.claude.json")
try:
    with open(path) as f:
        config = json.load(f)
except (OSError, ValueError):
    config = {}
config.setdefault("projects", {}).setdefault(os.getcwd(), {})["hasTrustDialogAccepted"] = True
with open(path, "w") as f:
    json.dump(config, f)
EOF
exec "$@"
