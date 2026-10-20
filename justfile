# Контейнер devenv для проекта, из которого запущен just: https://github.com/gelerum/devenv
# compose-файлы - из этой папки, со всеми локальными правками. Из main на GitHub - remote.just
# Ставится один раз (именно import, симлинк не подойдёт):
#   echo "import '$PWD/justfile'" > ~/.justfile

set quiet
# Без ">>>> Executing external compose provider" от podman
export PODMAN_COMPOSE_WARNING_LOGS := "false"

repo := source_directory()
# Откуда брать compose-файлы; remote.just подменяет на GitHub
src := repo + "/"
# Проект - корень git-репозитория или текущая папка
root := shell('git -C "$1" rev-parse --show-toplevel 2>/dev/null || echo "$1"', invocation_directory())
# compose принимает в имени проекта только [a-z0-9_-]
project := replace_regex(replace_regex(lowercase(file_name(root)), '[^a-z0-9_-]', ''), '^[_-]+', '')
container := project + "-dev-1"
local := if path_exists(root / "compose.local.yaml") == "true" { "-f compose.local.yaml" } else { "" }
gpu := if path_exists("/dev/nvidiactl") == "true" { "-f '" + src + "compose.gpu.yaml'" } else { "" }
# Без --progress quiet: прогресс скачивания образа
compose_loud := "cd '" + root + "' && podman compose -p " + project + " -f '" + src + "compose.base.yaml' " + local + " " + gpu
compose := replace(compose_loud, "podman compose", "podman compose --progress quiet")
worktrees := root + ".agent"
dotfiles := env("DEVENV_DOTFILES", parent_directory(repo) / "dotfiles")
agent := "podman compose --progress quiet -f '" + src + "compose.task.yaml' " + local + " " + gpu
# Общие тома external: создаём сами, чтобы compose не приписывал их первому проекту.
# Настройки уже лежат в синхронизируемой ~/.config/devenv/pi; не копируем и не перезаписываем.
volumes := "for f in settings.json models.json; do [ -f ~/.config/devenv/pi/$f ] && [ ! -L ~/.config/devenv/pi/$f ] || { echo \"Нужен обычный файл ~/.config/devenv/pi/$f; дождитесь Syncthing\" >&2; exit 1; }; done; mkdir -p ~/.claude/projects ~/.pi/agent/sessions ~/.pi/agent/memory ~/.local/share/devenv/nix; [ -e ~/.pi/agent/auth.json ] || (umask 077; echo '{}' > ~/.pi/agent/auth.json); for v in devenv-cache devenv-mason; do podman volume exists $v || podman volume create $v >/dev/null; done"

# compose только для создания: каждый его вызов ~1с
# Зайти в контейнер (поднимет, если не запущен); удаляется, когда выходит последний шелл
# [default]: без него just через import не считает рецепт рецептом по умолчанию
[default]
default:
    [ "$(podman inspect -f '{{{{.State.Running}}' {{container}} 2>/dev/null)" = true ] || { {{volumes}} && {{compose}} up -d -y; }
    -podman exec -it {{container}} zsh
    [ "$(podman inspect -f '{{{{len .ExecIDs}}' {{container}})" != 0 ] || podman rm -f {{container}} >/dev/null

up:
    {{volumes}}
    {{compose}} up -d -y

down:
    {{compose}} down

pull:
    {{compose_loud}} pull

# Собрать образ из Dockerfile (тег тот же, что у образа из CI). dotfiles - из соседней
# папки ../dotfiles или DEVENV_DOTFILES как есть, с незакоммиченными правками; нет папки - с GitHub
build:
    podman build -t "${DEVENV_IMAGE:-ghcr.io/gelerum/devenv:latest}" {{ if path_exists(dotfiles) == "true" { "--build-context dotfiles='" + dotfiles + "' --label devenv.dotfiles.ref=local" } else { "" } }} '{{repo}}'

# Агент в worktree <проект>.agent/<task> на ветке <task>
agent task:
    cd '{{root}}' && { [ -d '{{worktrees}}/{{task}}' ] || git worktree add '{{worktrees}}/{{task}}' '{{task}}' 2>/dev/null || git worktree add -b '{{task}}' '{{worktrees}}/{{task}}'; }
    {{volumes}}
    cd '{{root}}' && TASK='{{task}}' {{agent}} -p '{{replace_regex('agent-' + project + '-' + lowercase(task), '[^a-z0-9_-]', '-')}}' up -d -y

agent-shell task:
    podman exec -it '{{replace_regex('agent-' + project + '-' + lowercase(task), '[^a-z0-9_-]', '-')}}-dev-1' zsh

agent-down task:
    cd '{{root}}' && TASK='{{task}}' {{agent}} -p '{{replace_regex('agent-' + project + '-' + lowercase(task), '[^a-z0-9_-]', '-')}}' down
