# devenv

Docker-окружение для разработки: Ubuntu, zsh, Neovim, Claude Code и мои dotfiles. Защищает хост от агента.

## Запуск

Из корня проекта:

```sh
docker compose -p "${PWD##*/}" -f 'https://github.com/gelerum/devenv.git#main:compose.base.yaml' up -d
docker compose -p "${PWD##*/}" -f 'https://github.com/gelerum/devenv.git#main:compose.base.yaml' exec dev zsh
```

Проект монтируется по тому же пути, что и на хосте. На сервере с видеокартой добавьте второй файл: `-f 'https://github.com/gelerum/devenv.git#main:compose.gpu.yaml'`. Остановить: `... down`.

Нужен `~/.config/devenv/claude.env` с ключом для Claude Code.

## Агент в отдельном worktree

```sh
git worktree add ../myproj.agent/fix-login
TASK=fix-login docker compose -f 'https://github.com/gelerum/devenv.git#main:compose.task.yaml' up -d
```

## Языки

Версию берут из файлов проекта и скачивают сами:

| Язык   | Файл                                  | Команда                        |
|--------|---------------------------------------|--------------------------------|
| Go     | `go.mod`                              | `go ...`                       |
| Rust   | `rust-toolchain.toml`                 | `cargo ...`                    |
| Python | `.python-version`, `pyproject.toml`   | `uv sync`, `uv run ...`        |
| conda  | `environment.yml`                     | `conda env create -f environment.yml` |

LSP и форматтеры mason ставит при первом запуске `nvim`. `DEVENV_LANGS="go python"` - только для этих языков.

## Тома

История и память Claude Code - в `~/.claude/projects` на хосте (синхронизируется Syncthing).

Общие для всех проектов:

- `devenv-cache` - скачанные версии языков, окружения conda, кеши пакетов
- `devenv-mason` - LSP и форматтеры

## Обновления

Образ: `ghcr.io/gelerum/devenv`. CI собирает его:

- после push сюда;
- после push в dotfiles;
- каждый понедельник, обновив все версии (`scripts/update-versions.sh all`).

Все версии и хеши - в `Dockerfile`. Закрепить сборку: `DEVENV_IMAGE=ghcr.io/gelerum/devenv:sha-<коммит>` в `.env`.
