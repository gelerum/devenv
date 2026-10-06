# Версии и хеши обновляет scripts/update-versions.sh. Только linux/amd64.
ARG UBUNTU_VERSION=24.04
ARG UBUNTU_DIGEST=sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ARG APT_SNAPSHOT=20261005T000000Z
ARG BAT_VERSION=0.26.1
ARG BAT_SHA256=ad59954aa1540e526f97267f60557ea5ef4c7dcf91a0811254134537cb353a3c
ARG NVIM_VERSION=0.12.5
ARG NVIM_SHA256=bce0f56eda1f1b1db6eee8f4133d7a38813ea07933837dd1777411ca384c6875
ARG GO_VERSION=1.27.1
ARG GO_SHA256=63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445
ARG UV_VERSION=0.12.23
ARG UV_SHA256=9167d72b3319674b6303c4cbe071854bba13ebdf3d76b1a7cbdc175471fb66d6
ARG MINIFORGE_VERSION=26.7.2-0
ARG MINIFORGE_SHA256=281b0ac7d550802efc81af633225a5e6116d29ae72f3ab4eae7168c3931a4c05
ARG RUSTUP_VERSION=1.29.1
ARG RUSTUP_SHA256=dda7234360b7f578ca8b0ddcb80145646fa61a67c1720a5abc7051b35c9fcb71
ARG STARSHIP_VERSION=1.26.0
ARG STARSHIP_SHA256=b7c232b0e8249d8e55a40beb79c5c43a7d370f3f9408bd215deb0170daeaadf3
ARG FZF_VERSION=0.74.4
ARG FZF_SHA256=05e6813a337cc722c3ed07e54a764b75cc5d671e2e60459db0ba696ee5fa7504
ARG ZOXIDE_VERSION=0.10.0
ARG ZOXIDE_SHA256=2d93385b99f3e82cf2701609a1bffcad863fbeb75aa3fe7eb6be4d29be68b1ae
ARG SUPERFILE_VERSION=1.6.0
ARG SUPERFILE_SHA256=d45b0e95072629a6aa7983a84eedca9cd7a98861e67ef91be1415496e3dda309
ARG CLAUDE_CODE_VERSION=2.1.285
ARG CLAUDE_CODE_SHA256=33dad1ec615a2e08cc78b494f05c110e49916de2c79d78ec8799ebf46b233d29
ARG FZF_TAB_REF=24105b15714bfec37989ed5c5b6e60f572253019
ARG ZSH_HISTORY_SUBSTRING_SEARCH_REF=a0bdb0d47dbaba31dba2db7af8c48a5d9c74049a
# Скиллы Claude для Obsidian: коммит kepano/obsidian-skills
ARG OBSIDIAN_SKILLS_REF=3ccff5338ea700537839b21900aa5358a0402c98
ARG DOTFILES_REPO=https://github.com/gelerum/dotfiles
ARG DOTFILES_REF=a6aa14dbe05afa0ad1ceaf95b1125795ea247bf2
# Последний коммит dotfiles в папке nvim
ARG NVIM_REF=a6aa14dbe05afa0ad1ceaf95b1125795ea247bf2

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
      stow ripgrep fd-find eza \
      pkg-config libssl-dev libffi-dev zlib1g-dev libsqlite3-dev \
      nodejs npm python3 python3-venv \
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
    PIP_CACHE_DIR=/home/q/.cache/devenv/pip \
    CONDA_ENVS_PATH=/home/q/.cache/devenv/conda/envs \
    CONDA_PKGS_DIRS=/home/q/.cache/devenv/conda/pkgs
ENV PATH=/opt/conda/condabin:/usr/local/go/bin:$GOPATH/bin:$CARGO_HOME/bin:$PATH

ARG UID=1000
ARG GID=1000
RUN userdel -r ubuntu \
 && groupadd -g "$GID" q \
 && useradd -m -u "$UID" -g q -s /usr/bin/zsh q

USER q
ENV PATH=/home/q/.local/bin:$PATH
# Точки монтирования томов, чтобы тома принадлежали q
RUN mkdir -p ~/.cache/devenv ~/.local/share/nvim/mason

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
ARG DOTFILES_PACKAGES="zsh git starship claude terminfo bat"
RUN mkdir -p ~/.config ~/work \
 && cd /opt/dotfiles && stow -t ~ $DOTFILES_PACKAGES \
 && bat cache --build

LABEL devenv.dotfiles.ref=$DOTFILES_REF devenv.nvim.ref=$NVIM_REF

COPY entrypoint.sh /usr/local/bin/devenv-entrypoint

WORKDIR /home/q/work
ENTRYPOINT ["devenv-entrypoint"]
CMD ["sleep", "infinity"]
