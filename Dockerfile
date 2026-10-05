# Все версии и хеши зафиксированы здесь: одинаковые значения дают одинаковый образ.
# Обновляет их scripts/update-versions.sh. CI запускает его раз в неделю для всего
# и после каждого push в dotfiles — для DOTFILES_REF и NVIM_REF.
# Образ собирается только под linux/amd64: хеши посчитаны для amd64-файлов.
ARG UBUNTU_VERSION=24.04
ARG UBUNTU_DIGEST=sha256:a853f94d226358a79c740cfc7bce0c289748f3fe3488d921d038ccd752c61b60
# Снимок архива Ubuntu (https://snapshot.ubuntu.com): фиксирует версии apt-пакетов
ARG APT_SNAPSHOT=20261003T000000Z
ARG BAT_VERSION=0.26.1
ARG BAT_SHA256=ad59954aa1540e526f97267f60557ea5ef4c7dcf91a0811254134537cb353a3c
ARG NVIM_VERSION=0.12.5
ARG NVIM_SHA256=bce0f56eda1f1b1db6eee8f4133d7a38813ea07933837dd1777411ca384c6875
ARG GO_VERSION=1.27.1
ARG GO_SHA256=63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445
ARG STARSHIP_VERSION=1.26.0
ARG STARSHIP_SHA256=b7c232b0e8249d8e55a40beb79c5c43a7d370f3f9408bd215deb0170daeaadf3
ARG FZF_VERSION=0.74.4
ARG FZF_SHA256=05e6813a337cc722c3ed07e54a764b75cc5d671e2e60459db0ba696ee5fa7504
ARG ZOXIDE_VERSION=0.10.0
ARG ZOXIDE_SHA256=2d93385b99f3e82cf2701609a1bffcad863fbeb75aa3fe7eb6be4d29be68b1ae
ARG CLAUDE_CODE_VERSION=2.1.285
ARG CLAUDE_CODE_SHA256=33dad1ec615a2e08cc78b494f05c110e49916de2c79d78ec8799ebf46b233d29
# Плагины zsh, которых нет в apt: коммиты в их репозиториях
ARG FZF_TAB_REF=24105b15714bfec37989ed5c5b6e60f572253019
ARG ZSH_HISTORY_SUBSTRING_SEARCH_REF=a0bdb0d47dbaba31dba2db7af8c48a5d9c74049a
ARG DOTFILES_REPO=https://github.com/gelerum/dotfiles
ARG DOTFILES_REF=a6aa14dbe05afa0ad1ceaf95b1125795ea247bf2
# Последний коммит dotfiles, затрагивающий папку nvim
ARG NVIM_REF=a6aa14dbe05afa0ad1ceaf95b1125795ea247bf2

FROM ubuntu:${UBUNTU_VERSION}@${UBUNTU_DIGEST}
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 IN_CONTAINER=1

# Пакеты. Для snapshot.ubuntu.com нужен https, поэтому сначала ставим ca-certificates
ARG APT_SNAPSHOT
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && apt-get update -o APT::Update::Error-Mode=any --snapshot "$APT_SNAPSHOT" \
 && apt-get install -y --no-install-recommends --snapshot "$APT_SNAPSHOT" \
      ca-certificates curl git less unzip build-essential \
      zsh zsh-autosuggestions zsh-syntax-highlighting direnv \
      stow ripgrep fd-find eza \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /usr/bin/fdfind /usr/local/bin/fd

# Дальше всё скачивается с GitHub и проверяется по sha256.
# fetch <url> <sha256> <файл> — скачать и проверить
RUN printf '#!/bin/sh\nset -e\ncurl -fsSLo "$3" "$1"\necho "$2  $3" | sha256sum -c --quiet\n' > /usr/local/bin/fetch \
 && chmod +x /usr/local/bin/fetch

# bat (в Ubuntu старая версия без --theme-light/--theme-dark)
ARG BAT_VERSION BAT_SHA256
RUN fetch "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/bat_${BAT_VERSION}_amd64.deb" "$BAT_SHA256" /tmp/bat.deb \
 && dpkg -i /tmp/bat.deb \
 && rm /tmp/bat.deb

# fzf (в Ubuntu старая версия без `fzf --zsh`)
ARG FZF_VERSION FZF_SHA256
RUN fetch "https://github.com/junegunn/fzf/releases/download/v${FZF_VERSION}/fzf-${FZF_VERSION}-linux_amd64.tar.gz" "$FZF_SHA256" /tmp/fzf.tar.gz \
 && tar -xzf /tmp/fzf.tar.gz -C /usr/local/bin fzf \
 && rm /tmp/fzf.tar.gz

ARG ZOXIDE_VERSION ZOXIDE_SHA256
RUN fetch "https://github.com/ajeetdsouza/zoxide/releases/download/v${ZOXIDE_VERSION}/zoxide-${ZOXIDE_VERSION}-x86_64-unknown-linux-musl.tar.gz" "$ZOXIDE_SHA256" /tmp/zoxide.tar.gz \
 && tar -xzf /tmp/zoxide.tar.gz -C /usr/local/bin zoxide \
 && rm /tmp/zoxide.tar.gz

ARG STARSHIP_VERSION STARSHIP_SHA256
RUN fetch "https://github.com/starship/starship/releases/download/v${STARSHIP_VERSION}/starship-x86_64-unknown-linux-musl.tar.gz" "$STARSHIP_SHA256" /tmp/starship.tar.gz \
 && tar -xzf /tmp/starship.tar.gz -C /usr/local/bin starship \
 && rm /tmp/starship.tar.gz

ARG NVIM_VERSION NVIM_SHA256
RUN fetch "https://github.com/neovim/neovim/releases/download/v${NVIM_VERSION}/nvim-linux-x86_64.tar.gz" "$NVIM_SHA256" /tmp/nvim.tar.gz \
 && mkdir /opt/nvim \
 && tar -xzf /tmp/nvim.tar.gz -C /opt/nvim --strip-components=1 \
 && rm /tmp/nvim.tar.gz \
 && ln -s /opt/nvim/bin/nvim /usr/local/bin/nvim

# Go. Нужен и mason'у: gopls, goimports, gofumpt ставятся через go install
ARG GO_VERSION GO_SHA256
RUN fetch "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" "$GO_SHA256" /tmp/go.tar.gz \
 && tar -xzf /tmp/go.tar.gz -C /usr/local \
 && rm /tmp/go.tar.gz
ENV PATH=/usr/local/go/bin:$PATH

# Пользователь с вашим UID/GID
ARG UID=1000
ARG GID=1000
RUN userdel -r ubuntu \
 && groupadd -g "$GID" q \
 && useradd -m -u "$UID" -g q -s /usr/bin/zsh q

USER q
ENV PATH=/home/q/.local/bin:$PATH

# Плагины zsh, которых нет в apt. Пути — те, что ожидает .zshrc
ARG FZF_TAB_REF ZSH_HISTORY_SUBSTRING_SEARCH_REF
RUN for p in "Aloxaf/fzf-tab $FZF_TAB_REF" "zsh-users/zsh-history-substring-search $ZSH_HISTORY_SUBSTRING_SEARCH_REF"; do \
      set -- $p; d=~/.zsh/plugins/${1#*/}; \
      git init -q "$d" \
      && git -C "$d" fetch -q --depth 1 "https://github.com/$1" "$2" \
      && git -C "$d" checkout -q FETCH_HEAD \
      || exit 1; \
    done

# Claude Code. Автообновление выключено, чтобы версия в контейнере не уплывала
ENV DISABLE_AUTOUPDATER=1
ARG CLAUDE_CODE_VERSION CLAUDE_CODE_SHA256
RUN mkdir -p ~/.claude/projects ~/.local/share/nvim \
 && fetch "https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}/linux-x64/claude" "$CLAUDE_CODE_SHA256" /tmp/claude \
 && chmod +x /tmp/claude \
 && /tmp/claude install "$CLAUDE_CODE_VERSION" \
 && rm /tmp/claude \
 && echo '{"hasCompletedOnboarding": true, "theme": "auto", "projects": {"/work": {"hasTrustDialogAccepted": true}}}' > ~/.claude.json

# Конфиг и плагины Neovim — отдельный слой. Пересобирается, только когда меняется
# папка nvim в dotfiles (NVIM_REF), а не при любом коммите в dotfiles.
# Плагины ставятся по lazy-lock.json
USER root
ARG DOTFILES_REPO NVIM_REF
RUN git init -q /opt/nvim-config \
 && cd /opt/nvim-config \
 && git sparse-checkout set nvim \
 && git fetch -q --depth 1 --filter=blob:none "$DOTFILES_REPO" "$NVIM_REF" \
 && git checkout -q FETCH_HEAD \
 && chown -R q:q /opt/nvim-config

# NVIM_TOOLS=1 — поставить в образ парсеры treesitter, LSP-серверы и форматтеры (через mason).
# DEVENV_LANGS="go python" — только для этих языков, пусто — для всех (python lua rust go).
# Версии того, что ставит mason, не зафиксированы: с NVIM_TOOLS=1 образ воспроизводим не полностью
ARG NVIM_TOOLS=0
ARG DEVENV_LANGS=""
ARG APT_SNAPSHOT
RUN if [ "$NVIM_TOOLS" = 1 ]; then \
      apt-get update -o APT::Update::Error-Mode=any --snapshot "$APT_SNAPSHOT" \
      && apt-get install -y --no-install-recommends --snapshot "$APT_SNAPSHOT" nodejs npm python3-venv \
      && rm -rf /var/lib/apt/lists/*; \
    fi
# Тот же выбор действует и в контейнере: neovim не будет доставлять инструменты при запуске
ENV DEVENV_NVIM_TOOLS=$NVIM_TOOLS DEVENV_LANGS=$DEVENV_LANGS

USER q
RUN mkdir -p ~/.config \
 && stow -d /opt/nvim-config -t ~ nvim \
 && nvim --headless "+Lazy! restore" +qa \
 && if [ "$NVIM_TOOLS" = 1 ]; then nvim --headless "+MasonToolsInstallSync" +qa; fi

# Dotfiles: клон принадлежит q — изменения возможны только внутри контейнера,
# в репозиторий они не попадут, пересборка всё восстановит
USER root
ARG DOTFILES_REPO DOTFILES_REF
RUN git init -q /opt/dotfiles \
 && git -C /opt/dotfiles fetch -q --depth 1 "$DOTFILES_REPO" "$DOTFILES_REF" \
 && git -C /opt/dotfiles checkout -q FETCH_HEAD \
 && chown -R q:q /opt/dotfiles \
 && install -d -o q -g q /work

# Конфиги через stow. ~/.config создаём заранее, иначе stow заменит его целиком одной ссылкой
USER q
ARG DOTFILES_PACKAGES="zsh git starship claude terminfo bat"
RUN mkdir -p ~/.config \
 && cd /opt/dotfiles && stow -t ~ $DOTFILES_PACKAGES \
 && bat cache --build

LABEL devenv.dotfiles.ref=$DOTFILES_REF devenv.nvim.ref=$NVIM_REF

WORKDIR /work
CMD ["sleep", "infinity"]
