#!/bin/sh
# Вызывается через ~/.local/bin/{claude,codex,pi}; клиенты могут заменять ссылки
# настроек/credentials атомарной записью. Python сохраняет результат после выхода.
exec python3 /usr/local/lib/devenv/agent_storage.py launch "${0##*/}" "$@"
