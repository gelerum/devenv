#!/bin/sh
# Подготовить данные pi на хосте до запуска контейнера.
# В config — обычные файлы для Syncthing, не ссылки на dotfiles.
set -eu

dotfiles=${1:-}
agent=$HOME/.pi/agent
config=$HOME/.config/devenv/pi
mkdir -p "$agent/sessions" "$agent/memory" "$config"
tmp=''
trap 'if [ -n "$tmp" ]; then rm -f -- "$tmp"; fi' 0
trap 'exit 1' HUP INT TERM

# Авторизация остаётся отдельной от синхронизируемой конфигурации.
if [ -e "$agent/auth.json" ] || [ -L "$agent/auth.json" ]; then
    if [ ! -f "$agent/auth.json" ]; then
        printf 'Ожидался файл авторизации: %s\n' "$agent/auth.json" >&2
        exit 1
    fi
else
    (umask 077; printf '{}\n' > "$agent/auth.json")
fi

for name in settings.json models.json; do
    target=$config/$name
    if [ -L "$target" ] || { [ -e "$target" ] && [ ! -f "$target" ]; }; then
        printf 'Для Syncthing нужен обычный файл, не папка или ссылка: %s\n' "$target" >&2
        exit 1
    fi
    [ ! -f "$target" ] || continue

    # Миграция один раз: сначала настройки хостового pi, затем defaults из dotfiles.
    source=$agent/$name
    if [ ! -f "$source" ]; then
        source="$dotfiles/pi/.pi/agent/$name"
        if [ -z "$dotfiles" ] || [ ! -f "$source" ]; then
            source=''
        fi
    fi
    # Syncthing игнорирует .syncthing.*.tmp. Готовый файл публикуем hard-link'ом:
    # ln без -f атомарно откажется, если Syncthing уже создал target.
    tmp=$(mktemp "$config/.syncthing.pi-init.XXXXXX.tmp")
    if [ -n "$source" ]; then
        cp -L "$source" "$tmp"
    else
        printf '{}\n' > "$tmp"
    fi
    if ! ln -T "$tmp" "$target" 2>/dev/null; then
        if [ -L "$target" ] || [ ! -f "$target" ]; then
            printf 'Не удалось создать обычный файл конфигурации: %s\n' "$target" >&2
            exit 1
        fi
        # Другой запуск или Syncthing опередил нас — сохраняем его файл.
    fi
    rm -f -- "$tmp"
    tmp=''
done
