# Версии и хеши обновляет scripts/update-versions.sh. Только linux/amd64.
ARG UBUNTU_VERSION=24.04
ARG UBUNTU_DIGEST=sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8
ARG APT_SNAPSHOT=20261116T000000Z
ARG BAT_VERSION=0.26.1
ARG BAT_SHA256=ad59954aa1540e526f97267f60557ea5ef4c7dcf91a0811254134537cb353a3c
ARG NVIM_VERSION=0.12.6
ARG NVIM_SHA256=474430d53e6264f6d6dd18db42d6dc9df3a1b56ca9e88a325bbf860e1a811d87
ARG GO_VERSION=1.27.4
ARG GO_SHA256=7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840
ARG UV_VERSION=0.13.8
ARG UV_SHA256=5acfd9177cfecf0bf87578f059728215ccc884388988f55f7a65041b57387d91
ARG MINIFORGE_VERSION=26.9.4-2
ARG MINIFORGE_SHA256=bbaf16b3897da24c4be50315934ba74848f617b4495982841d6a0a60e0edbbdf
ARG NIX_VERSION=2.35.6
ARG NIX_SHA256=b12ab64a291e41846b9da37b7f56eafa7683deaa267bafb2ed43440ab2f45f13
ARG RUSTUP_VERSION=1.29.3
ARG RUSTUP_SHA256=b1c8cb14e30889e7e2999e6b69e62d9e9b9ffc0f4df8180564d306d9680e6c55
ARG STARSHIP_VERSION=1.27.0
ARG STARSHIP_SHA256=10c8eb4cb3b761d9bf59ea828444c2dab36c900b7d69a69e08814b286969df89
ARG FZF_VERSION=0.75.0
ARG FZF_SHA256=0d6640f83582d991cf429754baad64b07e3a4e439a6019670f4b91da1314141c
ARG ZOXIDE_VERSION=0.10.0
ARG ZOXIDE_SHA256=2d93385b99f3e82cf2701609a1bffcad863fbeb75aa3fe7eb6be4d29be68b1ae
ARG SUPERFILE_VERSION=1.6.0
ARG SUPERFILE_SHA256=d45b0e95072629a6aa7983a84eedca9cd7a98861e67ef91be1415496e3dda309
ARG LIBTEXPRINTF_VERSION=1.31
ARG LIBTEXPRINTF_SHA256=8ca5a11d387631a34979295f73f9a2eccc87e17c690dcd4c1454eb65a9e372bc
ARG CLAUDE_CODE_VERSION=2.1.311
ARG CLAUDE_CODE_SHA256=86dc1fcc69498159eaf15f446613e847010f9036bfbbdffd4c49350be8489ada
ARG CODEX_VERSION=0.169.0
ARG CODEX_SHA256=3b8ed091149cc63a59046b9f094bcfa21cdb4dda15ede441ce369bcee4a71ba0
ARG PI_VERSION=1.5.2
ARG PI_SHA256=811c6f2c9e7aaee252b5404252e556fb713aa209c1f7f924226aa77d4ef70cb5
ARG HINDSIGHT_VERSION=0.8.7
ARG HINDSIGHT_SHA256=f9ad8b8c7df8c363cf05dbbfd75089424ccd54aca0cfee27ae298e28a217567d
ARG BUN_VERSION=1.4.4
ARG BUN_SHA256=bf8ccbfb2b0b80159e0f9a6d15c55317add8077534dbc6130a3edb52fccb395c
ARG FZF_TAB_REF=24105b15714bfec37989ed5c5b6e60f572253019
ARG ZSH_HISTORY_SUBSTRING_SEARCH_REF=a0bdb0d47dbaba31dba2db7af8c48a5d9c74049a
# Скиллы Claude для Obsidian: коммит kepano/obsidian-skills
ARG OBSIDIAN_SKILLS_REF=398127736bd4ba42d767b1419fee1a927508370b
# Agent tools: native MCP servers, upstream skills and fast non-fixing Nix lint.
ARG NODE_VERSION=24.22.3
ARG NODE_SHA256=4f2b175a6d53a5c617a80dba2676238a0688cef28c6da4eba35c7d844e66fcfb
ARG STATIX_REF=d324490e45bcda1b664f28b6f88da8580deda76b
ARG DEADNIX_VERSION=1.3.1
ARG NIX_LINT_RUST_VERSION=1.99.1
ARG SERENA_REF=0cef825f802d5323f8cb4bda3a5af52bf704770f
ARG UNDERSTAND_ANYTHING_REF=b861852dda79273bd9d2e01c3160d42e2df510d2
ARG DOTFILES_REPO=https://github.com/gelerum/dotfiles
ARG DOTFILES_REF=96b9e178e00c123f0ef0547b0faf4781b59f8b5b

# dotfiles на зафиксированном коммите. Локальная сборка подменяет стадию dotfiles
# своей папкой: --build-context dotfiles=<путь> (just build), тогда клон не нужен
FROM ubuntu:${UBUNTU_VERSION}@${UBUNTU_DIGEST} AS dotfiles-git
ARG APT_SNAPSHOT DOTFILES_REPO DOTFILES_REF
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && apt-get update -o APT::Update::Error-Mode=any --snapshot "$APT_SNAPSHOT" \
 && apt-get install -y --no-install-recommends --snapshot "$APT_SNAPSHOT" git \
 && git init -q /dotfiles \
 && git -C /dotfiles fetch -q --depth 1 "$DOTFILES_REPO" "$DOTFILES_REF" \
 && git -C /dotfiles checkout -q FETCH_HEAD

FROM scratch AS dotfiles
COPY --from=dotfiles-git /dotfiles /

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

# Codex CLI - нативный пакет, без npm; SQLite локален для устройства. Голый бинарник
# не годится: TUI запускает фоновый сервер, которому нужны ресурсы пакета рядом с bin/
ENV CODEX_SQLITE_HOME=/home/q/.local/state/codex/sqlite
ARG CODEX_VERSION CODEX_SHA256
RUN fetch "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-package-x86_64-unknown-linux-musl.tar.gz" "$CODEX_SHA256" /tmp/codex.tar.gz \
 && mkdir /opt/codex \
 && tar -xzf /tmp/codex.tar.gz -C /opt/codex \
 && rm /tmp/codex.tar.gz \
 && ln -s /opt/codex/bin/codex /usr/local/bin/codex \
 && codex --version

# pi - бинарник на Bun, Node не нужен. Рядом с ним docs, theme и wasm, поэтому распаковывается целиком
ARG PI_VERSION PI_SHA256
RUN fetch "https://github.com/earendil-works/pi/releases/download/v${PI_VERSION}/pi-linux-x64.tar.gz" "$PI_SHA256" /tmp/pi.tar.gz \
 && mkdir /opt/pi \
 && tar -xzf /tmp/pi.tar.gz -C /opt/pi --strip-components=1 \
 && rm /tmp/pi.tar.gz \
 && ln -s /opt/pi/pi /usr/local/bin/pi
ENV PI_SKIP_VERSION_CHECK=1 PI_TELEMETRY=0
# Keep generated architecture graphs inside the active worktree; never redirect
# an isolated agent's writes into the main checkout (upstream's default).
ENV UNDERSTAND_NO_WORKTREE_REDIRECT=1

# bun - для зависимостей и тестов своих расширений pi
ARG BUN_VERSION BUN_SHA256
RUN fetch "https://github.com/oven-sh/bun/releases/download/bun-v${BUN_VERSION}/bun-linux-x64.zip" "$BUN_SHA256" /tmp/bun.zip \
 && unzip -qj /tmp/bun.zip bun-linux-x64/bun -d /usr/local/bin \
 && ln -s bun /usr/local/bin/bunx \
 && rm /tmp/bun.zip

# Ubuntu's Node 18 is too old for Understand Anything. The upstream tarball is
# pinned and replaces node/npm together; MCP servers never run npx @latest.
ARG NODE_VERSION NODE_SHA256
RUN fetch "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" "$NODE_SHA256" /tmp/node.tar.xz \
 && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
 && rm /tmp/node.tar.xz

COPY pi-tools/package.json pi-tools/package-lock.json /opt/pi-tools/
RUN cd /opt/pi-tools && npm ci --ignore-scripts --no-audit --no-fund \
 && ln -s /opt/pi-tools/node_modules/.bin/pnpm /usr/local/bin/pnpm
# Install Chromium and its OS libraries at build time, not on the first agent
# call. Profiles are isolated per session; this is NOT a security boundary.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
RUN printf 'APT::Snapshot "%s";\n' "$APT_SNAPSHOT" > /tmp/playwright-apt.conf \
 && APT_CONFIG=/tmp/playwright-apt.conf /opt/pi-tools/node_modules/.bin/playwright install --with-deps chromium \
 && chmod -R a+rX /opt/playwright-browsers \
 && rm -rf /var/lib/apt/lists/* /root/.npm /tmp/playwright-apt.conf
COPY pi-tools/serena-context.yml /opt/pi-tools/serena-context.yml

# Менеджеры версий: нужные версии языков скачиваются по файлам проекта в ~/.cache/devenv (том)
ARG GO_VERSION GO_SHA256
RUN fetch "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" "$GO_SHA256" /tmp/go.tar.gz \
 && tar -xzf /tmp/go.tar.gz -C /usr/local \
 && rm /tmp/go.tar.gz

ARG UV_VERSION UV_SHA256
RUN fetch "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" "$UV_SHA256" /tmp/uv.tar.gz \
 && tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv uv-x86_64-unknown-linux-gnu/uvx \
 && rm /tmp/uv.tar.gz

# Shared notebook IDE, separate from every project's scientific environment.
# uv.lock pins transitive wheels/hashes; system Python is pinned by the Ubuntu
# snapshot. Do not put this venv into the shared mutable project cache volume.
COPY jupyter/pyproject.toml jupyter/uv.lock /opt/jupyter/
RUN UV_PROJECT_ENVIRONMENT=/opt/jupyter/.venv UV_CACHE_DIR=/tmp/jupyter-uv-cache \
      uv sync --project /opt/jupyter --frozen --no-dev \
        --python /usr/bin/python3 --no-python-downloads \
 && rm -rf /tmp/jupyter-uv-cache
# Prebuild the local UI extension against the exact installed JupyterLab core.
# npm ci uses integrity hashes; no npm/download/build step on container startup.
# The content provider re-checks local edits after async fetch, before applying
# disk contents, instead of blindly reverting every two seconds.
COPY jupyter/notebook-autoreload /tmp/notebook-autoreload/
RUN cd /tmp/notebook-autoreload \
 && npm ci --ignore-scripts --no-audit --no-fund \
 && npm test \
 && /opt/jupyter/.venv/bin/jupyter-builder build \
      --core-package-file=/opt/jupyter/.venv/lib/python3.12/site-packages/jupyterlab/staging/package.json . \
 && mkdir -p /opt/jupyter/.venv/share/jupyter/labextensions/@devenv \
 && cp -a labextension /opt/jupyter/.venv/share/jupyter/labextensions/@devenv/notebook-autoreload \
 && rm -rf /tmp/notebook-autoreload /root/.npm
COPY scripts/jupyter_project.py /usr/local/lib/devenv/jupyter_project.py
RUN printf '#!/bin/sh\nexec /usr/bin/python3 /usr/local/lib/devenv/jupyter_project.py "$@"\n' \
      > /usr/local/bin/devenv-jupyter \
 && chmod +x /usr/local/bin/devenv-jupyter \
 && printf '#!/bin/sh\nexec /opt/jupyter/.venv/bin/ruff "$@"\n' > /usr/local/bin/devenv-ruff \
 && chmod +x /usr/local/bin/devenv-ruff

# Serena's own lock pins transitive Python dependencies. Keep a dedicated venv,
# no uvx downloads on startup and no dependency on any project's .venv.
ARG SERENA_REF
RUN git init -q /opt/serena \
 && git -C /opt/serena fetch -q --depth 1 https://github.com/oraios/serena "$SERENA_REF" \
 && git -C /opt/serena checkout -q FETCH_HEAD \
 && UV_CACHE_DIR=/tmp/serena-uv-cache uv sync --project /opt/serena --frozen --no-dev --no-editable \
      --python /usr/bin/python3 --no-python-downloads \
 && rm -rf /tmp/serena-uv-cache /opt/serena/.git

# Build the official skills' runtime once, with upstream's frozen pnpm lock.
# No curl | bash installer, no post-commit hooks and no automatic repo analysis.
ARG UNDERSTAND_ANYTHING_REF
RUN git init -q /opt/understand-anything \
 && git -C /opt/understand-anything fetch -q --depth 1 https://github.com/Egonex-AI/Understand-Anything "$UNDERSTAND_ANYTHING_REF" \
 && git -C /opt/understand-anything checkout -q FETCH_HEAD \
 && cd /opt/understand-anything/understand-anything-plugin \
 && pnpm install --frozen-lockfile \
 && pnpm --filter @understand-anything/core build \
 && rm -rf /opt/understand-anything/.git /root/.local/share/pnpm /root/.cache/node-gyp

COPY --chmod=755 scripts/understand-dashboard.sh /usr/local/bin/devenv-understand

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

# Statix on crates.io is an UNRELATED project. Build the Nix linter from the
# reviewed upstream commit, using its Cargo.lock; deadnix has a proper crate.
# The temporary Rust toolchain/cache never enter the final layer. Do not use
# cargo install statix or compile tools on the first edit in a session.
# rustup is a standalone pinned binary, not installed in this temporary
# CARGO_HOME. Its automatic self-update would fail after installing the toolchain
# ("rustup is not installed at ..."); do not update the pinned manager implicitly.
ARG STATIX_REF DEADNIX_VERSION NIX_LINT_RUST_VERSION
RUN export RUSTUP_HOME=/tmp/nix-lint-rustup CARGO_HOME=/tmp/nix-lint-cargo \
 && rustup toolchain install "$NIX_LINT_RUST_VERSION" --profile minimal --no-self-update \
 && export RUSTUP_TOOLCHAIN="$NIX_LINT_RUST_VERSION" \
 && cargo install --locked --git https://github.com/oppiliappan/statix --rev "$STATIX_REF" --root /tmp/nix-lint-bin statix \
 && cargo install --locked --version "$DEADNIX_VERSION" --root /tmp/nix-lint-bin deadnix \
 && install /tmp/nix-lint-bin/bin/statix /tmp/nix-lint-bin/bin/deadnix /usr/local/bin/ \
 && rm -rf /tmp/nix-lint-rustup /tmp/nix-lint-cargo /tmp/nix-lint-bin

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
 && useradd -m -u "$UID" -g q -s /usr/bin/zsh q \
 && install -d -o q -g q /opt/node_modules /opt/hindsight \
 && chown -R q:q /opt/understand-anything

# Nix без демона, от q. store и var/nix заранее, иначе nix уходит в chroot-хранилище
# в ~/.local/share/nix, а chroot в контейнере запрещён
RUN mkdir -p /nix/store /nix/var/nix /etc/nix \
 && chown -R q:q /nix \
 && printf 'build-users-group =\nexperimental-features = nix-command flakes\n' > /etc/nix/nix.conf

USER q
ENV PATH=/home/q/.local/bin:$PATH
# Точки монтирования томов, чтобы тома принадлежали q. ~/.pi/agent заранее,
# иначе stow сделает его ссылкой на dotfiles и pi будет писать auth.json туда
RUN mkdir -p ~/.cache/devenv ~/.local/share/nvim/mason ~/.pi/agent/sessions ~/.pi/agent/memory ~/.codex \
 && mkdir -p ~/.pi/agent/skills ~/.pi/agent/agents \
 && for skill in /opt/understand-anything/understand-anything-plugin/skills/*; do \
      [ ! -f "$skill/SKILL.md" ] || ln -s "$skill" ~/.pi/agent/skills/; \
    done \
 && for agent in /opt/understand-anything/understand-anything-plugin/agents/*.md; do \
      ln -s "$agent" ~/.pi/agent/agents/; \
    done

# Official installer stages a self-contained, bundled runtime (no npm deps).
# Its generated settings are a template, not the host's real settings. Runtime
# and skill live outside the live-mounted dotfiles and survive recreation.
ARG HINDSIGHT_VERSION HINDSIGHT_SHA256
RUN fetch "https://registry.npmjs.org/@vectorize-io/hindsight-coding-agents/-/hindsight-coding-agents-${HINDSIGHT_VERSION}.tgz" "$HINDSIGHT_SHA256" /tmp/hindsight.tgz \
 && mkdir /tmp/hindsight-package \
 && tar -xzf /tmp/hindsight.tgz -C /tmp/hindsight-package --strip-components=1 \
 && HOME=/opt/hindsight bun /tmp/hindsight-package/dist/installer.js install pi \
      --server self-hosted --api-url http://calculation.tailnet.internal:9078 \
 && rm -rf /tmp/hindsight-package /tmp/hindsight.tgz

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
 && mv ~/.local/bin/claude ~/.local/bin/claude-native \
 && echo '{"hasCompletedOnboarding": true, "theme": "auto"}' > ~/.claude.json

# Только три скилла из плагина obsidian, без остальных
# The pinned revision uses a plugin monorepo layout, not a root skills/ directory.
# Validate every entry point before copying so layout changes fail explicitly.
ARG OBSIDIAN_SKILLS_REF
RUN git init -q /tmp/obsidian-skills \
 && cd /tmp/obsidian-skills \
 && git sparse-checkout set plugins/obsidian/skills/obsidian-markdown plugins/obsidian/skills/json-canvas plugins/obsidian/skills/obsidian-bases \
 && git fetch -q --depth 1 --filter=blob:none https://github.com/kepano/obsidian-skills "$OBSIDIAN_SKILLS_REF" \
 && git checkout -q FETCH_HEAD \
 && for skill in obsidian-markdown json-canvas obsidian-bases; do \
      test -s "plugins/obsidian/skills/$skill/SKILL.md" || { echo "Missing Obsidian skill: $skill" >&2; exit 1; }; \
    done \
 && mkdir -p ~/.claude/skills \
 && cp -r plugins/obsidian/skills/. ~/.claude/skills/ \
 && rm -rf /tmp/obsidian-skills

# Отдельный слой: пересобирается, только когда меняется папка nvim в dotfiles
COPY --from=dotfiles --chown=q:q nvim /opt/nvim-config/nvim
RUN mkdir -p ~/.config \
 && stow -d /opt/nvim-config -t ~ nvim \
 && nvim --headless "+Lazy! restore" +qa

COPY --from=dotfiles --chown=q:q . /opt/dotfiles

# ~/.config заранее, иначе stow заменит его целиком одной ссылкой
ARG DOTFILES_PACKAGES="zsh git starship claude pi terminfo bat"
RUN mkdir -p ~/.config \
 && cd /opt/dotfiles && stow -t ~ $DOTFILES_PACKAGES \
 && bat cache --build

# Fail the published build if its pinned dotfiles omit the chat UI or Stow
# leaves the extension undiscoverable. A successful build must include it.
RUN test -s /opt/dotfiles/pi/.pi/agent/extensions/chat-ui.ts \
 && test -s "$HOME/.pi/agent/extensions/chat-ui.ts"

# Зависимости локальных расширений pi (anthropic-oauth). В /opt/node_modules, а не
# рядом с расширениями: compose.local монтирует dotfiles поверх /opt/dotfiles и
# спрятал бы их. Модули ищутся вверх по пути, так что /opt/node_modules находится.
# Кеш bun - не в слой образа
RUN mkdir /tmp/pi-ext \
 && cp ~/.pi/agent/extensions/package.json /tmp/pi-ext/ \
 && cd /tmp/pi-ext \
 && BUN_INSTALL_CACHE_DIR=/tmp/bun-cache bun install --production \
 && cp -a node_modules/. /opt/node_modules/ \
 && rm -rf /tmp/pi-ext /tmp/bun-cache

# Exercise the bundled browser as the actual unprivileged runtime user. This
# catches missing .so dependencies during image build without visiting a site.
RUN node --input-type=module -e '\
  const { chromium } = await import("/opt/pi-tools/node_modules/playwright/index.mjs"); \
  const browser = await chromium.launch({ headless: true, chromiumSandbox: false }); \
  try { \
    const page = await browser.newPage(); \
    await page.setContent("<title>pi-tools-smoke</title><h1>Ready</h1>"); \
    if (await page.title() !== "pi-tools-smoke") throw new Error("Browser smoke failed"); \
  } finally { await browser.close(); }'

ARG DOTFILES_REF
LABEL devenv.dotfiles.ref=$DOTFILES_REF

# Без телеметрии, история Claude Code хранится 200 лет. Managed settings, чтобы
# не конфликтовать с ~/.claude/settings.json из dotfiles
COPY managed-settings.json /etc/claude-code/managed-settings.json
COPY entrypoint.sh /usr/local/bin/devenv-entrypoint
COPY scripts/agent_storage.py /usr/local/lib/devenv/agent_storage.py
COPY --chmod=755 agent-launcher.sh /usr/local/bin/devenv-agent
RUN for agent in claude codex pi; do ln -s /usr/local/bin/devenv-agent "$HOME/.local/bin/$agent"; done

WORKDIR /home/q
ENTRYPOINT ["devenv-entrypoint"]
CMD ["sleep", "infinity"]
