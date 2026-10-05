#!/usr/bin/env bash
# Обновляет зафиксированные версии и хеши в Dockerfile до последних.
#   scripts/update-versions.sh dotfiles — только коммиты dotfiles
#   scripts/update-versions.sh all      — всё: Ubuntu, снимок apt, инструменты, dotfiles
# GITHUB_TOKEN (необязательно) снимает лимит запросов к API GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."

mode=${1:?укажите dotfiles или all}

arg() { sed -n "s/^ARG $1=//p" Dockerfile; }
set_arg() { sed -i -E "s|^ARG $1=.*|ARG $1=$2|" Dockerfile; }

# Версия и sha256 файла из последнего релиза на GitHub. В имени файла {v} заменяется на версию
github_release() {
	local repo=$1 asset=$2 json v
	json=$(curl -fsSL ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
		"https://api.github.com/repos/$repo/releases/latest")
	v=$(jq -r '.tag_name | ltrimstr("v")' <<<"$json")
	asset=${asset//\{v\}/$v}
	echo "$v" "$(jq -r --arg a "$asset" '.assets[] | select(.name == $a) | .digest | ltrimstr("sha256:")' <<<"$json")"
}

update_dotfiles() {
	local dir
	dir=$(mktemp -d)
	git clone -q --filter=blob:none --no-checkout "$(arg DOTFILES_REPO)" "$dir"
	set_arg DOTFILES_REF "$(git -C "$dir" rev-parse HEAD)"
	set_arg NVIM_REF "$(git -C "$dir" log -1 --format=%H HEAD -- nvim)"
	rm -rf "$dir"
}

update_tools() {
	local token v sha json

	token=$(curl -fsSL "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/ubuntu:pull" | jq -r .token)
	set_arg UBUNTU_DIGEST "$(curl -fsSI -H "Authorization: Bearer $token" \
		-H 'Accept: application/vnd.oci.image.index.v1+json' \
		-H 'Accept: application/vnd.docker.distribution.manifest.list.v2+json' \
		"https://registry-1.docker.io/v2/library/ubuntu/manifests/$(arg UBUNTU_VERSION)" |
		tr -d '\r' | sed -n 's/^docker-content-digest: //Ip')"

	set_arg APT_SNAPSHOT "$(date -u +%Y%m%dT000000Z)"

	read -r v sha < <(github_release sharkdp/bat 'bat_{v}_amd64.deb')
	set_arg BAT_VERSION "$v" && set_arg BAT_SHA256 "$sha"

	read -r v sha < <(github_release neovim/neovim nvim-linux-x86_64.tar.gz)
	set_arg NVIM_VERSION "$v" && set_arg NVIM_SHA256 "$sha"

	read -r v sha < <(github_release starship/starship starship-x86_64-unknown-linux-musl.tar.gz)
	set_arg STARSHIP_VERSION "$v" && set_arg STARSHIP_SHA256 "$sha"

	read -r v sha < <(github_release junegunn/fzf 'fzf-{v}-linux_amd64.tar.gz')
	set_arg FZF_VERSION "$v" && set_arg FZF_SHA256 "$sha"

	read -r v sha < <(github_release ajeetdsouza/zoxide 'zoxide-{v}-x86_64-unknown-linux-musl.tar.gz')
	set_arg ZOXIDE_VERSION "$v" && set_arg ZOXIDE_SHA256 "$sha"

	set_arg FZF_TAB_REF "$(git ls-remote https://github.com/Aloxaf/fzf-tab HEAD | cut -f1)"
	set_arg ZSH_HISTORY_SUBSTRING_SEARCH_REF "$(git ls-remote https://github.com/zsh-users/zsh-history-substring-search HEAD | cut -f1)"

	json=$(curl -fsSL 'https://go.dev/dl/?mode=json')
	set_arg GO_VERSION "$(jq -r '.[0].version | ltrimstr("go")' <<<"$json")"
	set_arg GO_SHA256 "$(jq -r '.[0].files[] | select(.os == "linux" and .arch == "amd64" and .kind == "archive") | .sha256' <<<"$json")"

	v=$(curl -fsSL https://downloads.claude.ai/claude-code-releases/stable)
	set_arg CLAUDE_CODE_VERSION "$v"
	set_arg CLAUDE_CODE_SHA256 "$(curl -fsSL "https://downloads.claude.ai/claude-code-releases/$v/manifest.json" | jq -r '.platforms["linux-x64"].checksum')"
}

case $mode in
dotfiles) update_dotfiles ;;
all) update_tools && update_dotfiles ;;
*) echo "неизвестный режим: $mode" >&2 && exit 1 ;;
esac

# Пустое значение значит, что что-то не нашлось: лучше упасть, чем закоммитить битый Dockerfile
if grep -qE '^ARG [A-Z_]+(_VERSION|_SHA256|_DIGEST|_REF|_SNAPSHOT)=$' Dockerfile; then
	grep -nE '^ARG [A-Z_]+=$' Dockerfile >&2
	exit 1
fi
