# Версии и хеши обновляет scripts/update-versions.sh. Только linux/amd64.
ARG UBUNTU_VERSION=24.04
ARG UBUNTU_DIGEST=sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ARG APT_SNAPSHOT=20261012T000000Z
ARG BAT_VERSION=0.26.1
ARG BAT_SHA256=ad59954aa1540e526f97267f60557ea5ef4c7dcf91a0811254134537cb353a3c
ARG NVIM_VERSION=0.12.6
ARG NVIM_SHA256=474430d53e6264f6d6dd18db42d6dc9df3a1b56ca9e88a325bbf860e1a811d87
ARG GO_VERSION=1.27.2
ARG GO_SHA256=ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5
ARG UV_VERSION=0.13.0
ARG UV_SHA256=1468ebd5a5541121837c5a2817b9972ba6090fa6caa3d142620850a47fb75154
ARG MINIFORGE_VERSION=26.7.2-0
ARG MINIFORGE_SHA256=281b0ac7d550802efc81af633225a5e6116d29ae72f3ab4eae7168c3931a4c05
ARG NIX_VERSION=2.35.3
ARG NIX_SHA256=6ce3ce3703fdc241b560cba401c5d338042122fe5b1a81e07bf1a623f259eba0
ARG RUSTUP_VERSION=1.29.1
ARG RUSTUP_SHA256=dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71
ARG STARSHIP_VERSION=1.26.0
ARG STARSHIP_SHA256=b7c232b0e8249d8e55a40beb79c5c43a7d370f3f9408bd215deb0170daeaadf3
ARG FZF_VERSION=0.74.5
ARG FZF_SHA256=d47d7f882972c7d674dbbba998ffa4116e68379616ffac7695d0671e9a722c5f
ARG ZOXIDE_VERSION=0.10.0
ARG ZOXIDE_SHA256=2d93385b99f3e82cf2701609a1bffcad863fbeb75aa3fe7eb6be4d29be68b1ae
ARG SUPERFILE_VERSION=1.6.0
ARG SUPERFILE_SHA256=d45b0e95072629a6aa7983a84eedca9cd7a98861e67ef91be1415496e3dda309
ARG LIBTEXPRINTF_VERSION=1.31
ARG LIBTEXPRINTF_SHA256=8ca5a11d387631a34979295f73f9a2eccc87e17c690dcd4c1454eb65a9e372bc
ARG CLAUDE_CODE_VERSION=2.1.287
ARG CLAUDE_CODE_SHA256=3920489a5109cff5786a1a392c25277408ff22bc796d5edb9c16a60e5a1718f0
ARG PI_VERSION=1.3.0
ARG PI_SHA256=24f5be328b66d4da36876296989501974f43ab8434fbb57c35c523a3ea505ded
ARG BUN_VERSION=1.4.3
ARG BUN_SHA256=3e730528d89775f03f87f05c06787c4df4099d0a37f3f252e7b829cb23816e18
ARG FZF_TAB_REF=24105b15714bfec37989ed5c5b6e60f572253019
ARG ZSH_HISTORY_SUBSTRING_SEARCH_REF=a0bdb0d47dbaba31dba2db7af8c48a5d9c74049a
# Скиллы Claude для Obsidian: коммит kepano/obsidian-skills
ARG OBSIDIAN_SKILLS_REF=3ccff5338ea700537839b21900aa5358a0402c98
ARG DOTFILES_REPO=https://github.com/gelerum/dotfiles
ARG DOTFILES_REF=73bdba37d616493659f80aa031eafa811db883c1
# Последний коммит dotfiles в папке nvim
ARG NVIM_REF=70ba5c42e36b1550a35f6e07af32cb2fe789a341

FROM ubuntu:${UBUNTU_VERSION}@${UBUNTU_DIGEST}
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 IN_CONTAINER=1

# Для snapshot.ubuntu.com нужен https, поэтому сначала ca-certificates
ARG APT_SNAPSHOT
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && apt-get update -o APT::Update::Error-Mode=any --snapshot "$APT_SNAPSHOT" \
 && apt-get install -y --no-install-recommends --snapshot "$APT_SNAPSHOT" \
      ca-certificates curl git less unzip build-essential \
      zsh zsh-autosuggestions zsh-syntax-highlighting direnv \
      stow ripgrep fd-find eza poppler-utils shellcheck \
      pkg-config libssl-dev libffi-dev zlib1g-dev libsqlite3-dev \
      nodejs npm python3 python3-venv xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /usr/bin/fdfind /usr/local/bin/fd

# fetch <url> <sha256> <файл> - скачать и проверить хеш
RUN printf '#!/bin/sh\nset -e\ncurl -fsSL --retry 5 --retry-all-errors -o "$3" "$1"\necho "$2  $3" | sha256sum -c --quiet\n' > /usr/local/bin/fetch \
 && chmod +x /usr/local/bin/fetch

ARG BAT_VERSION BAT_SHA256
RUN fetch "https://github.com/sharkdp/bat/releases/download/v${BAT_VERSION}/bat_${BAT_VERSION}_amd64.deb" "$BAT_SHA256" /tmp/bat.deb \
 && dpkg -i /tmp/bat.deb \
 && rm /tmp/bat.deb

ARG FZF_VERSION FZF_SHA256
RUN fetch "https://github.com/junegunn/fzf/releases/download/v${FZF_VERSION}/fzf-${FZF_VERSION}-linux_amd64.tar.gz" "$FZF_SHA256" /tmp/fzf.tar.gz \
 && tar -xzf /tmp/fzf.tar.gz -C /usr/local/bin fzf \
 && rm /tmp/fzf.tar.gz

ARG ZOXIDE_VERSION ZOXIDE_SHA256
RUN fetch "https://github.com/ajeetdsouza/zoxide/releases/download/v${ZOXIDE_VERSION}/zoxide-${ZOXIDE_VERSION}-x86_64-unknown-linux-musl.tar.gz" "$ZOXIDE_SHA256" /tmp/zoxide.tar.gz \
 && tar -xzf /tmp/zoxide.tar.gz -C /usr/local/bin zoxide \
 && rm /tmp/zoxide.tar.gz

ARG SUPERFILE_VERSION SUPERFILE_SHA256
RUN fetch "https://github.com/yorukot/superfile/releases/download/v${SUPERFILE_VERSION}/superfile-linux-v${SUPERFILE_VERSION}-amd64.tar.gz" "$SUPERFILE_SHA256" /tmp/superfile.tar.gz \
 && tar -xzf /tmp/superfile.tar.gz -C /usr/local/bin --strip-components=3 "./dist/superfile-linux-v${SUPERFILE_VERSION}-amd64/spf" \
 && rm /tmp/superfile.tar.gz

# utftex - формулы LaTeX в Unicode-текст. Пакета в Ubuntu нет, собирается из исходников
ARG LIBTEXPRINTF_VERSION LIBTEXPRINTF_SHA256
RUN fetch "https://github.com/bartp5/libtexprintf/releases/download/v${LIBTEXPRINTF_VERSION}/libtexprintf-${LIBTEXPRINTF_VERSION}.tar.gz" "$LIBTEXPRINTF_SHA256" /tmp/libtexprintf.tar.gz \
 && tar -xzf /tmp/libtexprintf.tar.gz -C /tmp \
 && cd "/tmp/libtexprintf-${LIBTEXPRINTF_VERSION}" \
 && ./configure --prefix=/usr/local \
 && make -j"$(nproc)" \
 && make install \
 && ldconfig \
 && cd / && rm -rf /tmp/libtexprintf*

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

# pi - бинарник на Bun, Node не нужен. Рядом с ним docs, theme и wasm, поэтому распаковывается целиком
ARG PI_VERSION PI_SHA256
RUN fetch "https://github.com/earendil-works/pi/releases/download/v${PI_VERSION}/pi-linux-x64.tar.gz" "$PI_SHA256" /tmp/pi.tar.gz \
 && mkdir /opt/pi \
 && tar -xzf /tmp/pi.tar.gz -C /opt/pi --strip-components=1 \
 && rm /tmp/pi.tar.gz \
 && ln -s /opt/pi/pi /usr/local/bin/pi
ENV PI_SKIP_VERSION_CHECK=1 PI_TELEMETRY=0

# bun - для зависимостей и тестов своих расширений pi
ARG BUN_VERSION BUN_SHA256
RUN fetch "https://github.com/oven-sh/bun/releases/download/bun-v${BUN_VERSION}/bun-linux-x64.zip" "$BUN_SHA256" /tmp/bun.zip \
 && unzip -qj /tmp/bun.zip bun-linux-x64/bun -d /usr/local/bin \
 && ln -s bun /usr/local/bin/bunx \
 && rm /tmp/bun.zip

# Менеджеры версий: нужные версии языков скачиваются по файлам проекта в ~/.cache/devenv (том)
ARG GO_VERSION GO_SHA256
RUN fetch "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" "$GO_SHA256" /tmp/go.tar.gz \
 && tar -xzf /tmp/go.tar.gz -C /usr/local \
 && rm /tmp/go.tar.gz

ARG UV_VERSION UV_SHA256
RUN fetch "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" "$UV_SHA256" /tmp/uv.tar.gz \
 && tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv uv-x86_64-unknown-linux-gnu/uvx \
 && rm /tmp/uv.tar.gz

# Хук для conda activate - в системном /etc/zsh/zshrc, а не в .zshrc из dotfiles
ARG MINIFORGE_VERSION MINIFORGE_SHA256
RUN fetch "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-${MINIFORGE_VERSION}-Linux-x86_64.sh" "$MINIFORGE_SHA256" /tmp/miniforge.sh \
 && bash /tmp/miniforge.sh -b -p /opt/conda \
 && rm /tmp/miniforge.sh \
 && /opt/conda/bin/conda config --system --set auto_activate false \
 && /opt/conda/bin/conda clean -afy \
 && printf '\n# conda activate\neval "$(/opt/conda/bin/conda shell.zsh hook)"\n' >> /etc/zsh/zshrc

# Nix: официальный архив - готовые пути /nix/store. Весь /nix - папка хоста
# ~/.local/share/devenv/nix, поэтому пути лежат в /opt/nix и entrypoint копирует их туда.
# Ссылки в /usr/local/bin ведут в /nix/store и оживают после первого старта
ARG NIX_VERSION NIX_SHA256
RUN fetch "https://releases.nixos.org/nix/nix-${NIX_VERSION}/nix-${NIX_VERSION}-x86_64-linux.tar.xz" "$NIX_SHA256" /tmp/nix.tar.xz \
 && mkdir /opt/nix \
 && tar -xJf /tmp/nix.tar.xz -C /opt/nix --strip-components=1 \
 && rm /tmp/nix.tar.xz \
 && nix=$(ls -d /opt/nix/store/*-nix-"$NIX_VERSION") \
 && echo "/nix/store/${nix##*/}" > /opt/nix/nix-path \
 && for b in "$nix"/bin/*; do ln -s "/nix/store/${nix##*/}/bin/${b##*/}" /usr/local/bin/; done

# rustup-init - тот же бинарник, что rustup и cargo/rustc: роль выбирается по имени файла
ARG RUSTUP_VERSION RUSTUP_SHA256
RUN fetch "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/x86_64-unknown-linux-gnu/rustup-init" "$RUSTUP_SHA256" /usr/local/bin/rustup \
 && chmod +x /usr/local/bin/rustup \
 && for p in cargo rustc rustdoc rustfmt cargo-fmt cargo-clippy clippy-driver rust-analyzer rust-gdb rust-lldb; do \
      ln -s rustup "/usr/local/bin/$p"; \
    done

ENV GOPATH=/home/q/.cache/devenv/go \
    GOCACHE=/home/q/.cache/devenv/go-build \
    UV_CACHE_DIR=/home/q/.cache/devenv/uv \
    UV_PYTHON_INSTALL_DIR=/home/q/.cache/devenv/uv-python \
    RUSTUP_HOME=/home/q/.cache/devenv/rustup \
    CARGO_HOME=/home/q/.cache/devenv/cargo \
    npm_config_cache=/home/q/.cache/devenv/npm \
    BUN_INSTALL_CACHE_DIR=/home/q/.cache/devenv/bun \
    PIP_CACHE_DIR=/home/q/.cache/devenv/pip \
    NIX_CACHE_HOME=/home/q/.cache/devenv/nix \
    CONDA_ENVS_PATH=/home/q/.cache/devenv/conda/envs \
    CONDA_PKGS_DIRS=/home/q/.cache/devenv/conda/pkgs
ENV PATH=/opt/conda/condabin:/usr/local/go/bin:$GOPATH/bin:$CARGO_HOME/bin:$PATH

ARG UID=1000
ARG GID=1000
RUN userdel -r ubuntu \
 && groupadd -g "$GID" q \
 && useradd -m -u "$UID" -g q -s /usr/bin/zsh q

# Nix без демона, от q. store и var/nix заранее, иначе nix уходит в chroot-хранилище
# в ~/.local/share/nix, а chroot в контейнере запрещён
RUN mkdir -p /nix/store /nix/var/nix /etc/nix \
 && chown -R q:q /nix \
 && printf 'build-users-group =\nexperimental-features = nix-command flakes\n' > /etc/nix/nix.conf

USER q
ENV PATH=/home/q/.local/bin:$PATH
# Точки монтирования томов, чтобы тома принадлежали q. ~/.pi/agent заранее,
# иначе stow сделает его ссылкой на dotfiles и pi будет писать auth.json туда
RUN mkdir -p ~/.cache/devenv ~/.local/share/nvim/mason ~/.pi/agent/sessions ~/.pi/agent/memory

# Плагины zsh, которых нет в apt
ARG FZF_TAB_REF ZSH_HISTORY_SUBSTRING_SEARCH_REF
RUN for p in "Aloxaf/fzf-tab $FZF_TAB_REF" "zsh-users/zsh-history-substring-search $ZSH_HISTORY_SUBSTRING_SEARCH_REF"; do \
      set -- $p; d=~/.zsh/plugins/${1#*/}; \
      git init -q "$d" \
      && git -C "$d" fetch -q --depth 1 "https://github.com/$1" "$2" \
      && git -C "$d" checkout -q FETCH_HEAD \
      || exit 1; \
    done

ENV DISABLE_AUTOUPDATER=1
ARG CLAUDE_CODE_VERSION CLAUDE_CODE_SHA256
RUN mkdir -p ~/.claude/projects ~/.local/share/nvim \
 && fetch "https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION}/linux-x64/claude" "$CLAUDE_CODE_SHA256" /tmp/claude \
 && chmod +x /tmp/claude \
 && /tmp/claude install "$CLAUDE_CODE_VERSION" \
 && rm /tmp/claude \
 && echo '{"hasCompletedOnboarding": true, "theme": "auto"}' > ~/.claude.json

# Только три скилла из плагина obsidian, без остальных
ARG OBSIDIAN_SKILLS_REF
RUN git init -q /tmp/obsidian-skills \
 && cd /tmp/obsidian-skills \
 && git sparse-checkout set skills/obsidian-markdown skills/json-canvas skills/obsidian-bases \
 && git fetch -q --depth 1 --filter=blob:none https://github.com/kepano/obsidian-skills "$OBSIDIAN_SKILLS_REF" \
 && git checkout -q FETCH_HEAD \
 && mkdir -p ~/.claude/skills \
 && cp -r skills/. ~/.claude/skills/ \
 && rm -rf /tmp/obsidian-skills

# Отдельный слой: пересобирается, только когда меняется папка nvim в dotfiles
USER root
ARG DOTFILES_REPO NVIM_REF
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

USER root
ARG DOTFILES_REPO DOTFILES_REF
RUN git init -q /opt/dotfiles \
 && git -C /opt/dotfiles fetch -q --depth 1 "$DOTFILES_REPO" "$DOTFILES_REF" \
 && git -C /opt/dotfiles checkout -q FETCH_HEAD \
 && chown -R q:q /opt/dotfiles

# ~/.config заранее, иначе stow заменит его целиком одной ссылкой
USER q
ARG DOTFILES_PACKAGES="zsh git starship claude pi terminfo bat"
RUN mkdir -p ~/.config \
 && cd /opt/dotfiles && stow -t ~ $DOTFILES_PACKAGES \
 && bat cache --build

# Зависимости локальных расширений pi (anthropic-oauth). Кеш bun - не в слой образа
RUN cd ~/.pi/agent/extensions \
 && BUN_INSTALL_CACHE_DIR=/tmp/bun-cache bun install --production \
 && rm -rf /tmp/bun-cache

LABEL devenv.dotfiles.ref=$DOTFILES_REF devenv.nvim.ref=$NVIM_REF

# Без телеметрии, история Claude Code хранится 200 лет. Managed settings, чтобы
# не конфликтовать с ~/.claude/settings.json из dotfiles
COPY managed-settings.json /etc/claude-code/managed-settings.json
COPY entrypoint.sh /usr/local/bin/devenv-entrypoint

WORKDIR /home/q
ENTRYPOINT ["devenv-entrypoint"]
CMD ["sleep", "infinity"]
