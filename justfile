# Контейнер devenv для проекта, из которого запущен just: https://github.com/gelerum/devenv
# Ставится один раз: ln -s ~/work/devenv/justfile ~/.justfile

devenv := "https://github.com/gelerum/devenv.git#main:"
# Проект - корень git-репозитория или текущая папка
root := shell('git -C "$1" rev-parse --show-toplevel 2>/dev/null || echo "$1"', invocation_directory())
project := lowercase(file_name(root))
local := if path_exists(root / "compose.local.yaml") == "true" { "-f compose.local.yaml" } else { "" }
gpu := if path_exists("/dev/nvidiactl") == "true" { "-f '" + devenv + "compose.gpu.yaml'" } else { "" }
compose := "cd '" + root + "' && podman compose -p " + project + " -f '" + devenv + "compose.base.yaml' " + local + " " + gpu
worktrees := root + ".agent"
agent := "podman compose -f '" + devenv + "compose.task.yaml' " + local + " " + gpu

# Зайти в контейнер (поднимет, если не запущен)
default: up
    {{compose}} exec dev zsh

up:
    {{compose}} up -d -y

down:
    {{compose}} down

pull:
    {{compose}} pull
    {{compose}} up -d -y

# Агент в worktree <проект>.agent/<task> на ветке <task>
agent task:
    cd '{{root}}' && { [ -d {{worktrees}}/{{task}} ] || git worktree add {{worktrees}}/{{task}} {{task}} 2>/dev/null || git worktree add -b {{task}} {{worktrees}}/{{task}}; }
    cd '{{root}}' && TASK={{task}} {{agent}} -p agent-{{project}}-{{task}} up -d -y

agent-shell task:
    cd '{{root}}' && TASK={{task}} {{agent}} -p agent-{{project}}-{{task}} exec dev zsh

agent-down task:
    cd '{{root}}' && TASK={{task}} {{agent}} -p agent-{{project}}-{{task}} down
