# devenv

Окружение для разработки в rootless podman: Ubuntu, zsh, Neovim, Claude Code, pi и мои dotfiles. Защищает хост от агента.

## Запуск

Через [just](https://github.com/casey/just) из любой папки проекта. Один раз, из клона этого репо (симлинк не подойдёт, нужен именно import):

```sh
echo "import '$PWD/justfile'" > ~/.justfile      # compose-файлы из клона, с локальными правками
echo "import '$PWD/remote.just'" > ~/.justfile   # или из main на GitHub
```

| Команда                 | Что делает                                                        |
|-------------------------|-------------------------------------------------------------------|
| `just`                  | зайти в контейнер; удаляется, когда выходит последний шелл        |
| `just up` / `just down` | поднять в фоне / удалить                                          |
| `just pull`             | скачать свежий образ (контейнер подхватит его при пересоздании)  |
| `just build`            | собрать образ из `Dockerfile` с локальными dotfiles (см. ниже)   |
| `just agent <task>`     | агент в worktree `<проект>.agent/<task>` на ветке `<task>`        |
| `just agent-shell <task>` / `just agent-down <task>` | зайти к агенту / удалить его контейнер |

`compose.local.yaml` в корне проекта подключается автоматически.

Без just, из корня проекта:

```sh
podman compose -p "${PWD##*/}" -f 'https://github.com/gelerum/devenv.git#main:compose.base.yaml' up -d
podman compose -p "${PWD##*/}" -f 'https://github.com/gelerum/devenv.git#main:compose.base.yaml' exec dev zsh
```

Проект монтируется по тому же пути, что и на хосте. На сервере с видеокартой добавьте второй файл: `-f 'https://github.com/gelerum/devenv.git#main:compose.gpu.yaml'`. Остановить: `... down`.

Нужно:

- `~/.config/devenv/claude.env` с ключом для Claude Code (необязательно, можно войти в контейнере);
- `systemctl --user enable --now podman.socket` - `podman compose` работает через docker-compose v2 и этот сокет;
- без just - один раз создать общие тома и файлы для pi (из клона devenv):

  ```sh
  podman volume create devenv-cache
  podman volume create devenv-mason
  mkdir -p ~/.claude/projects ~/.pi/agent/sessions ~/.pi/agent/memory ~/.local/share/devenv/nix
  [ -e ~/.pi/agent/auth.json ] || (umask 077; printf '{}\n' > ~/.pi/agent/auth.json)
  ```

До запуска дождитесь синхронизации `~/.config/devenv/pi/`: в ней должны быть
обычные файлы `settings.json` и `models.json`. Это единственный источник настроек
pi для контейнеров. `just` проверяет наличие файлов, но не создаёт и не копирует
конфигурацию из dotfiles или хостового `~/.pi/agent/`.
На новом компьютере подключите эту папку к Syncthing и дождитесь обоих файлов.

## Свой образ

`just build` собирает образ под тем же тегом, что у образа из CI, и `just` дальше использует его (`just pull` вернёт образ из CI). dotfiles берутся из `../dotfiles` рядом с этим репо или из `DEVENV_DOTFILES` - как есть, с незакоммиченными правками, без доступа к GitHub-репо dotfiles. Если папки нет, они клонируются на коммите `DOTFILES_REF`. Остальное (Ubuntu, бинарники) всё равно скачивается из сети.

## Агент в отдельном worktree

```sh
git worktree add ../myproj.agent/fix-login
TASK=fix-login podman compose -f 'https://github.com/gelerum/devenv.git#main:compose.task.yaml' up -d
```

## Языки

Версию берут из файлов проекта и скачивают сами:

| Язык   | Файл                                  | Команда                        |
|--------|---------------------------------------|--------------------------------|
| Go     | `go.mod`                              | `go ...`                       |
| Rust   | `rust-toolchain.toml`                 | `cargo ...`                    |
| Python | `.python-version`, `pyproject.toml`   | `uv sync`, `uv run ...`        |
| conda  | `environment.yml`                     | `conda env create -f environment.yml` |
| Nix    | `flake.nix`                           | `nix develop`                  |

LSP и форматтеры mason ставит при первом запуске `nvim`. `DEVENV_LANGS="go python"` - только для этих языков.

## Тома

История и память Claude Code - в `~/.claude/projects` на хосте. Для pi общий
Compose монтирует `~/.pi/agent/sessions`, `memory` и `auth.json` как раньше.
Настройки подключаются отдельной папкой:

```text
Хост:       ~/.config/devenv/pi/ → /run/pi-config в контейнере
Контейнер:  ~/.pi/agent/settings.json → /run/pi-config/settings.json
            ~/.pi/agent/models.json   → /run/pi-config/models.json
```

Ссылки создаёт entrypoint при старте. Выбор дефолтной модели через Ctrl+S в `/model`
пишется в `~/.config/devenv/pi/settings.json` на хосте. Весь остальной `~/.pi/agent`
не перекрывается. В папке конфигурации должны быть обычные файлы, не ссылки наружу.

Для перехода нужен готовый образ с обновлённым entrypoint: после публикации через
CI выполните на хосте `just pull`, затем `just down` и `just`. Локальная сборка
не нужна. Запущенные контейнеры не получают новые mounts автоматически.

### Два компьютера: что синхронизировать

| Данные | Путь на хосте | Как переносить |
|---|---|---|
| Сессии pi | `~/.pi/agent/sessions/` | Syncthing; не продолжать одну сессию одновременно на двух компьютерах |
| Память pi, включая общую и проектную | `~/.pi/agent/memory/` | Syncthing; проверять конфликты при одновременном редактировании |
| Настройки pi для контейнеров | `~/.config/devenv/pi/` целиком | Syncthing; внутри обычные `settings.json` и `models.json` |
| Расширения, темы, агенты и инструкции | пакет `pi/` в dotfiles | Git или Syncthing; зависимости расширений устанавливать на каждом компьютере |
| Проектные настройки и инструкции | `.pi/`, `AGENTS.md`, `CLAUDE.md` внутри проектов | Вместе с проектом, обычно Git |
| История и проектная память Claude Code | `~/.claude/projects/` | Syncthing, если продолжаете использовать Claude Code |

Папка конфигурации смонтирована целиком: замена JSON через Syncthing/rename
видна контейнеру без пересоздания. Но pi может держать настройки в памяти:
после внешнего изменения перечитайте конфигурацию (`/reload`, `/model`) или
перезапустите pi. Дождитесь синхронизации перед переходом на второй компьютер;
одновременное изменение одного конфига из нескольких pi может создать конфликт.
Dotfiles остаются источником расширений, тем и агентов, но не содержат рабочие
`settings.json` и `models.json` контейнеров.

На обоих компьютерах желательно иметь одинаковые абсолютные пути проектов
(например, `/home/q/2_Code/myproject`): pi группирует сессии по рабочей папке,
а расширение памяти также использует путь проекта. При разных путях сессия может
не появиться в обычном списке текущего проекта; её можно открыть явно через
`pi --session <путь-к-файлу>`.

`auth.json` и `~/.config/devenv/claude.env` содержат секреты: не добавляйте их в Git.
Для двух компьютеров рекомендуется отдельный `/login` на каждом, без постоянной
синхронизации `auth.json`: ротация OAuth refresh-токенов и запаздывающая синхронизация
могут привести к потере актуальных credentials. Сессии и память переносятся без
переноса авторизации. Они тоже могут содержать приватные данные проекта.

Не требуется синхронизировать `models-store.json` (кеш каталога), `node_modules`,
кеши языков, `/nix` и тома Podman — их можно восстановить на каждом компьютере.

Общие для всех проектов:

- `devenv-cache` - скачанные версии языков, окружения conda, кеши пакетов
- `devenv-mason` - LSP и форматтеры
- `~/.local/share/devenv/nix` - `/nix` контейнера, отдельный от `/nix` хоста. Почистить: `nix-collect-garbage -d` в контейнере

## Обновления

Образ: `ghcr.io/gelerum/devenv`. CI собирает его:

- после push сюда;
- после push в dotfiles;
- каждый понедельник, обновив все версии (`scripts/update-versions.sh all`).

Все версии и хеши - в `Dockerfile`. Закрепить сборку: `DEVENV_IMAGE=ghcr.io/gelerum/devenv:sha-<коммит>` в `.env`.
