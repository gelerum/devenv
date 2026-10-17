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

# Nix из образа (/opt/nix) - в /nix: при первом старте и после обновления образа.
# Каждый путь копируется во временную папку и переименовывается, чтобы параллельный
# старт другого контейнера не увидел недокопированный путь. Без cp -a: оно переносит
# SELinux-метку образа с категориями этого контейнера, и другие контейнеры не смогут читать
nix=$(cat /opt/nix/nix-path)
# /nix - папка хоста, а не том: содержимое /nix образа в неё не копируется
mkdir -p /nix/store /nix/var/nix
if [ ! -e "/nix/var/nix/devenv-${nix##*/}" ]; then
	for p in /opt/nix/store/*; do
		t=/nix/store/${p##*/}
		[ -e "$t" ] && continue
		tmp=$t.tmp-$(hostname)
		cp -dR --preserve=mode,timestamps "$p" "$tmp" && { mv -T "$tmp" "$t" 2>/dev/null || { chmod -R u+w "$tmp"; rm -rf "$tmp"; }; }
	done
	"$nix/bin/nix-store" --load-db < /opt/nix/.reginfo
	# Корень для сборщика мусора: иначе nix-collect-garbage удалит сам nix
	mkdir -p /nix/var/nix/gcroots
	ln -sfn "$nix" /nix/var/nix/gcroots/devenv-nix
	touch "/nix/var/nix/devenv-${nix##*/}"
fi

exec "$@"
