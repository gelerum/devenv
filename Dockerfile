# Все версии зафиксированы здесь. Одинаковые значения дают одинаковый образ.
# DOTFILES_REF и NVIM_REF обновляет CI (.github/workflows/image.yaml) после push в dotfiles.
ARG UBUNTU_DIGEST=sha256:a853f94d226358a79c740cfc7bce0c289748f3fe3488d921d038ccd752c61b60
# Снимок архива Ubuntu (https://snapshot.ubuntu.com): фиксирует версии apt-пакетов
ARG APT_SNAPSHOT=20261001T000000Z
ARG BAT_VERSION=0.26.1
ARG NVIM_VERSION=0.12.5
ARG GO_VERSION=1.27.1
ARG STARSHIP_VERSION=1.26.0
ARG CLAUDE_CODE_VERSION=2.1.285
ARG DOTFILES_REPO=https://github.com/gelerum/dotfiles
ARG DOTFILES_REF=3b80befce334c767071c1dbdde8ceedd12d6fc53
# Последний коммит dotfiles, затрагивающий папку nvim
ARG NVIM_REF=26fa4a0be2876bcca957ae46936d75b3884297d5

FROM ubuntu:24.04@${UBUNTU_DIGEST}
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 IN_CONTAINER=1

# Инструменты. Для snapshot.ubuntu.com нужен https, поэтому сначала ставим ca-certificates
ARG APT_SNAPSHOT
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && apt-get update -o APT::Update::Error-Mode=any --snapshot "$APT_SNAPSHOT" \
 && apt-get install -y --no-install-recommends --snapshot "$APT_SNAPSHOT" \
      ca-certificates curl git less unzip build-essential \
      zsh stow ripgrep fd-find eza \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /usr/bin/fdfind /usr/local/bin/fd

# bat из релизов GitHub (в Ubuntu старая версия без --theme-light/--theme-dark)
ARG BAT_VERSION
RUN curl -fsSLo /tmp/bat.deb "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/bat_${BAT_VERSION}_$(dpkg --print-architecture).deb" \
 && dpkg -i /tmp/bat.deb \
 && rm /tmp/bat.deb

# Neovim
ARG NVIM_VERSION
RUN mkdir /opt/nvim \
 && curl -fsSL "https://github.com/neovim/neovim/releases/download/v${NVIM_VERSION}/nvim-linux-$(uname -m | sed s/aarch64/arm64/).tar.gz" \
    | tar -xz -C /opt/nvim --strip-components=1 \
 && ln -s /opt/nvim/bin/nvim /usr/local/bin/nvim

# Go. Нужен и mason'у: gopls, goimports, gofumpt ставятся через go install
ARG GO_VERSION
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-$(dpkg --print-architecture).tar.gz" | tar -xz -C /usr/local
ENV PATH=/usr/local/go/bin:$PATH

# Starship
ARG STARSHIP_VERSION
RUN curl -fsSL https://starship.rs/install.sh | sh -s -- -y --version "v${STARSHIP_VERSION}"

# Пользователь с вашим UID/GID
ARG UID=1000
ARG GID=1000
RUN userdel -r ubuntu \
 && groupadd -g "$GID" q \
 && useradd -m -u "$UID" -g q -s /usr/bin/zsh q

# Claude Code. Автообновление выключено, чтобы версия в контейнере не уплывала
USER q
ENV PATH=/home/q/.local/bin:$PATH DISABLE_AUTOUPDATER=1
ARG CLAUDE_CODE_VERSION
RUN mkdir -p ~/.claude/projects ~/.local/share/nvim \
 && curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_CODE_VERSION" \
 && echo '{"hasCompletedOnboarding": true, "theme": "auto", "projects": {"/work": {"hasTrustDialogAccepted": true}}}' > ~/.claude.json

# Конфиг и плагины Neovim — отдельный слой. Пересобирается, только когда меняется
# папка nvim в dotfiles (NVIM_REF), а не при любом коммите в dotfiles.
# Плагины ставятся по lazy-lock.json
USER root
ARG DOTFILES_REPO
ARG NVIM_REF
RUN git init -q /opt/nvim-config \
 && cd /opt/nvim-config \
 && git sparse-checkout set nvim \
 && git fetch -q --depth 1 --filter=blob:none "$DOTFILES_REPO" "$NVIM_REF" \
 && git checkout -q FETCH_HEAD \
 && chown -R q:q /opt/nvim-config

USER q
RUN mkdir -p ~/.config \
 && stow -d /opt/nvim-config -t ~ nvim \
 && nvim --headless "+Lazy! restore" +qa
# Если используете mason-tool-installer, раскомментируйте:
# RUN nvim --headless "+MasonToolsInstallSync" +qa

# Dotfiles: клон принадлежит q — изменения возможны только внутри контейнера,
# в репозиторий они не попадут, пересборка всё восстановит
USER root
ARG DOTFILES_REPO
ARG DOTFILES_REF
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

WORKDIR /work
CMD ["sleep", "infinity"]
