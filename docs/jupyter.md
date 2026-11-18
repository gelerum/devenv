# JupyterLab: IDE в образе, kernel в проекте

Один образ devenv, **отдельный контейнер и Jupyter-сервер на проект**.
В `/opt/jupyter/.venv` установлены JupyterLab, jupyterlab-lsp,
jupyterlab-code-formatter, basedpyright и Ruff. Версии и транзитивные зависимости
закреплены в `jupyter/pyproject.toml` и `jupyter/uv.lock`.
Научные библиотеки и `ipykernel` остаются в `.venv` проекта, не в IDE-окружении.
Нативный Jupyter-сервис NixOS и общий доступ к чужим kernels не нужны.

## Порты на calculation

Резерв для проектных веб-интерфейсов — **19200–19299**, блоками по 10:

| Проект | Блок | Loopback хоста → порт контейнера |
|---|---|---|
| blockchain-thesis | 19200–19209 | Jupyter `19200 → 8888` |
| ligand-based-generation | 19210–19219 | Jupyter `19210 → 8888`, MLflow `19211 → 9287` |
| будущие проекты | 19220–19299 | пока не назначены |

Это соглашение, не автоматический allocator. В конфигурации infra сервисов в
этом диапазоне нет; перед запуском на **хосте** проверьте живые listeners:

```sh
ss -ltn '( sport >= :19200 and sport <= :19299 )'
```

`8888` хоста уже используется SearXNG. Порт `8888` **внутри** каждого
изолированного контейнера с ним не конфликтует. Не включайте host network.
Новые firewall-правила, rathole-пробросы и публичные listeners не требуются.

В `compose.local.yaml` каждого проекта, сохраняя существующие mounts:

```yaml
services:
  dev:
    environment:
      DEVENV_JUPYTER_HOST_PORT: "${BLOCKCHAIN_JUPYTER_PORT:-19200}"
    ports:
      - "127.0.0.1:${BLOCKCHAIN_JUPYTER_PORT:-19200}:8888"
```

Для ligand замените переменную на `LIGAND_JUPYTER_PORT`, значение на `19210`
и добавьте `127.0.0.1:${LIGAND_MLFLOW_PORT:-19211}:9287`.
У ligand этот файл исключён из Git: повторите настройки на каждой машине вручную.
Переменные позволяют переопределить **внешние** порты; измените также SSH-пробросы
и allowed-hosts/CORS MLflow. `DEVENV_JUPYTER_HOST_PORT` нужен для правильного URL,
а не для настройки listener Jupyter.

## Однократная подготовка на calculation

Нужны актуальные клоны devenv и проектов, Podman/Compose/just и уже настроенное
хранилище агентов (см. основной README). Используйте локальный `justfile`, чтобы
рецепты и compose соответствовали этим изменениям, а не старому main:

```sh
cd /home/q/2_Code/devenv
echo "import '$PWD/justfile'" > ~/.justfile
just build
```

До пересоздания старых контейнеров сохраните ноутбуки, остановите вычисления
и штатно завершите агентов. `just down` **уничтожает процессы и kernels**,
но не проектную папку. Не выполняйте его в контейнере с активной работой.
После сборки на хосте, отдельно для каждого проекта:

```sh
cd /home/q/2_Code/blockchain-thesis  # затем повторить для ligand-based-generation
just down                         # только когда старую работу можно остановить
just up
just                              # войти в проектный контейнер
```

В открывшемся контейнере:

```sh
uv sync --locked                  # dev-группа с ipykernel включена по умолчанию
devenv-jupyter --check            # проверить инструменты/kernel без запуска сервера
exit
```

Не переносите `.venv` с ноутбука на сервер: на каждой машине создавайте её через
`uv sync --locked`. JupyterLab из проектных зависимостей удалён;
`uv run jupyter lab` больше не является способом запуска IDE.

## Обычный запуск и браузер на ноутбуке

На **хосте calculation** из корня нужного проекта:

```sh
just jupyter          # создать контейнер при необходимости, запустить IDE detached
just jupyter-status   # статус и путь к логу, без token
just jupyter-url      # URL с секретным token
```

На **ноутбуке**, в отдельном терминале:

```sh
ssh -N -o ExitOnForwardFailure=yes \
  -L 19200:127.0.0.1:19200 \
  -L 19210:127.0.0.1:19210 \
  -L 19211:127.0.0.1:19211 calculation-ts
```

`calculation-ts` — SSH-алиас tailnet из настроек ноутбука. Если его нет,
используйте `q@calculation.tailnet.internal` или свой рабочий SSH-алиас.
В браузере откройте URL из `just jupyter-url`: `http://127.0.0.1:19200/lab?token=…`
или `http://127.0.0.1:19210/lab?token=…`. Это HTTP внутри SSH, не HTTPS.
MLflow запускается отдельно командой из README ligand и доступен на `19211`.

Закрытие браузера, SSH-проброса или последнего `just`-шелла не останавливает IDE
и kernel. После переподключения поднимите SSH-проброс заново и откройте URL.
Контейнеры не обещают пережить reboot; несохранённые ячейки и память kernel
не являются персистентными. На calculation reboot также требует физической
разблокировки LUKS.

Можно выполнять всё локально на ноутбуке: там нужен тот же собранный образ,
проектный compose и своя `.venv`; SSH-проброс не нужен. Для лёгкой работы это
тот же workflow, но вычисления идут на ноутбуке, не на calculation.

## Тема Catppuccin

В образ включён `catppuccin-jupyterlab`. По умолчанию включена **Adaptive Theme**:
**Catppuccin Latte** для светлой системной темы браузера (день), **Catppuccin Mocha**
для тёмной (ночь). Переключение следует настройке ОС на устройстве с браузером,
а не часам сервера. Если ОС переключает тему по расписанию, Jupyter следует ему.
Ручной выбор в **Settings → Theme** сохраняется при перезапуске; существующий
файл настроек темы не перезаписывается. После обновления образа и пересоздания
проектного контейнера перезапустите Jupyter и обновите страницу браузера.

## Шрифт кода

По умолчанию CodeMirror использует **JetBrainsMono Nerd Font, 16 CSS px** —
эквивалент Ghostty `font-size = 12` (pt). Это штатные настройки
**Settings → Settings Editor → CodeMirror → Default editor configuration →
customStyles**, общие для ячеек и файлов, без пользовательского CSS.
Шрифт должен быть установлен на устройстве с браузером; иначе используется
`monospace`. Ручные настройки CodeMirror сохраняются при перезапуске.

В Ghostty явно включены `calt` и `liga`; у JupyterLab нет эквивалентной штатной
настройки для этих OpenType-функций. Здесь их не форсируем: отображение лигатур
остаётся стандартным поведением браузера и шрифта.

## IDE и проверки

Launcher определяет Git-корень текущего checkout и разрешает **только его kernel**.
`sys.executable` в ячейке должен быть `<проект>/.venv/bin/python`.
Basedpyright настроен на этот же Python и `standard` type checking.
Настройки проекта задаются в `pyproject.toml` (`tool.basedpyright`, `tool.ruff`).

- Подсказки, hover, переходы и type diagnostics — basedpyright через JupyterLab-LSP.
- Сортировка импортов, затем форматирование при сохранении — Ruff.
- Полный lint внутри проектного контейнера:

  ```sh
  devenv-ruff check path/to/notebook.ipynb
  # Исправления — только по явному желанию:
  devenv-ruff check --fix path/to/notebook.ipynb
  devenv-ruff format path/to/notebook.ipynb
  ```

Ruff LSP одновременно с basedpyright не запускается: inline Ruff-диагностика
не обещается. Браузерный UI не является точной копией двух LSP Neovim.

## Остановка и диагностика

```sh
just jupyter-status
just jupyter-url      # секрет: не публиковать вывод
just jupyter-stop     # останавливает сервер И kernels; сначала сохранить работу
```

Из контейнера доступны те же команды: `devenv-jupyter --status/--url/--stop`.
Повторный `just jupyter` при работающем или ещё запускающемся сервере откажет,
а не создаст второй. При медленном старте `--status` показывает
`starting-or-unresponsive`: живой процесс сохраняет контейнер даже до готовности
HTTP. Запись процесса проверяется по PID, времени старта и boot ID, чтобы не
доверять старому PID после пересоздания контейнера. `--url` и `--stop` требуют
готового HTTP API; если процесс завис до его запуска, смотрите лог, затем
при необходимости остановите контейнер (это завершит и остальные процессы).
После остановки контейнер остаётся; `just down` удалит его, когда работа закончена.
При занятости контейнерного порта launcher не выбирает другой порт молча.

Конфиги, runtime и лог находятся в приватном `~/.cache/devenv/jupyter/<hash>/`
(общий cache-volume, разделение по абсолютному пути проекта и порту).
Конфиг и лог могут содержать token; не коммитьте и не публикуйте их.
Ошибки старта смотрите в `server.log`, путь показывает `--status` для живого сервера.
`--check` также показывает каталог состояния. Токен генерируется при каждом старте.
Не отключайте auth и не меняйте loopback-публикацию на `0.0.0.0`.

## Проверки разработки devenv

Быстрые unit-тесты (без установки зависимостей и без контейнеров):

```sh
python3 -m unittest discover -s tests -p test_jupyter_project.py -v
```

Opt-in smoke-тесты запускают только временный синтетический сервер/kernel,
проверяют auth, kernel Python, LSP completion/diagnostics, Ruff и схемы настроек.
Подготовьте отдельные тестовые venv, не научные окружения проектов:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/devenv-jupyter-tools uv sync --project jupyter --locked
uv venv --python 3.12 /tmp/devenv-jupyter-kernel
uv pip install --python /tmp/devenv-jupyter-kernel/bin/python 'ipykernel==7.4.0'
DEVENV_TEST_JUPYTER_TOOLS=/tmp/devenv-jupyter-tools \
DEVENV_TEST_JUPYTER_KERNEL=/tmp/devenv-jupyter-kernel/bin/python \
/tmp/devenv-jupyter-tools/bin/python -m unittest discover -s tests -p test_jupyter_runtime.py -v
```

Эти тесты не заменяют сборку образа и проверку Podman/Compose на целевом хосте.
