# Инструменты pi: код, документация, браузер и Nix lint

## Что подключено

| Инструмент | Интеграция | Где закреплён |
|---|---|---|
| Statix 0.5.8 | существующий `lint.ts`, после `write` / `edit` `.nix` | upstream git commit + Cargo.lock, Rust toolchain в Dockerfile |
| Deadnix 1.3.1 | тот же хук, без `--edit` | точная версия crate + `--locked` |
| Context7 | официальный HTTP MCP, без отдельного плагина | endpoint в dotfiles `pi/.pi/agent/mcp.json` |
| Playwright MCP 0.0.85 | официальный stdio MCP + Chromium | `pi-tools/package-lock.json`; браузер скачивается при сборке |
| Serena | официальный stdio MCP, интерфейс `tools` | upstream git commit + frozen uv.lock |
| Understand Anything | upstream skills + определения subagents | upstream git commit + frozen pnpm-lock.yaml |

Источники: [Statix](https://github.com/oppiliappan/statix),
[Deadnix](https://github.com/astro/deadnix),
[Context7](https://github.com/upstash/context7),
[Playwright MCP](https://github.com/microsoft/playwright-mcp),
[Serena](https://github.com/oraios/serena),
[Understand Anything](https://github.com/Egonex-AI/Understand-Anything).

У Context7 есть готовое расширение `@upstash/context7-pi`, но здесь оно не нужно:
у установленного pi уже есть MCP. Аналогично не ставим старые MCP-adapter плагины,
которые могут заменить встроенную поддержку и перестать читать `mcp.json`.
HTTP Context7 — внешний изменяемый сервис, не воспроизводимый локальный артефакт.

## Применить

Из **хостового** shell, не из работающего контейнера:

```sh
cd ~/2_Code/devenv
just build   # соседний ../dotfiles подхватывается вместе с локальными изменениями
```

После завершения текущих агентов/вычислений пересоздать нужный проектный контейнер.
Обычный `just up` не гарантирует замену уже работающего контейнера новым образом:
в проекте выполнить `just down`, затем `just up`. Это останавливает процессы
контейнера, включая Jupyter, поэтому сначала сохранить работу.

При сборке из GitHub нужен опубликованный dotfiles-коммит с новым `mcp.json` и
lint-хуком; локальная сборка через `just build` не требует предварительного коммита.

В новом контейнере:

```sh
pi mcp list
# внутри pi: /mcp — состояние, /reload — перечитать конфигурацию
python3 -m unittest discover -s /path/to/devenv/tests -p test_pi_tools.py -v
DEVENV_TEST_PI_TOOLS=1 python3 -m unittest discover -s /path/to/devenv/tests -p test_pi_tools.py -v
```

`pi mcp list` проверяет подключение, но не запускает браузер и не доказывает
работоспособность LSP. Для браузера попросить pi открыть тестовую страницу;
для Serena — получить символы небольшого файла проекта.

`mcp.json` поступает из Stow/dotfiles. Не сохранять туда токены через `/mcp`:
локальные секреты должны оставаться вне Git/Syncthing config. Для переопределений
можно использовать проектный `.pi/mcp.json` в доверенном проекте. Учесть: если
указывать только `enabled`/`exposure`, pi наследует остальные поля; при замене
`url`/`command` нужно задать полную запись сервера.

## Nix lint

После успешного `write` / `edit` автоматически выполняются:

```sh
statix check --format errfmt path/to/file.nix
deadnix --output-format json path/to/file.nix
```

Statix читает `statix.toml` из корня проекта. Deadnix поддерживает inline skip
прагмы upstream. Неиспользуемые аргументы модулей иногда намеренные — хук не
исправляет исходники, не форматирует и не запускает `nix flake check`.
Отсутствующий бинарник пропускается. Проверки через `bash` и MCP-редактирование
хуком не наблюдаются: после них агент обязан запустить проверки явно.

Важно: crate `statix` на crates.io — **другой проект**. Поэтому Nix Statix
собирается из `oppiliappan/statix` по коммиту, а не через `cargo install statix`.

Тесты хука в соседнем dotfiles: `bun test tests/pi-lint.test.ts`.

## Serena: только код, без второй памяти

`pi-tools/serena-context.yml` задаёт фиксированный allowlist 13 инструментов:
символы, references, diagnostics, rename, safe delete и symbol-level edits.
**Память, onboarding, shell и REPL отсутствуют на стороне сервера**, а не просто
скрыты из списка инструментов модели. Включён готовый upstream mode `no-memories`;
`mem` API дополнительно исключён и в нашем context.
Hindsight остаётся единственной долговременной памятью агента. Отдельного моста
Serena ↔ Hindsight нет: их совместно использует pi.

`--project-from-cwd` выбирает текущий репозиторий/worktree. Serena может создавать
`.serena/project.yml` и индексы: это служебная конфигурация/кеш, не разговорная
память. Не коммитить кеши и логи. Dashboard не запускается и порты не публикуются.

**Языковые серверы — отдельные зависимости.** Некоторые Serena загружает сама
при первом использовании; далеко не все языки работают полностью offline.
Для Nix нужен `nixd` и рабочий Nix. В образ `nixd` не включён; без него upstream
может попытаться установить его через Nix. Чтобы использовать версию из lock
проекта, заранее запустить из корня Nix flake:

```sh
nix shell --inputs-from . nixpkgs#nixd --command pi
```

Так `nixd` доступен дочернему MCP-серверу через PATH. Это может потребовать сети
и cache.nixos.org; не считать установку языковых серверов частью мгновенного lint.
Для остальных языков смотреть prerequisites соответствующего LSP в Serena.

## Context7

Endpoint работает без API key, но с лимитами. При их достижении можно настроить
ключ отдельно по документации Context7; здесь секрет не создаётся и не требуется.
В запросы не передавать приватные исходники и секреты. Указывать библиотеку и
версию из проекта; для NixOS дополнительно проверять закреплённый nixpkgs.
Для автономной работы без внешнего интернета использовать локальные docs/source.

## Playwright

Отдельный headless Chromium, `--isolated`: пользовательские cookies и профиль
не подключаются. Браузер и системные библиотеки устанавливаются при сборке образа,
не при первом вызове. Библиотеки берутся с APT snapshot образа.
Не добавляем capabilities, privileged и проброс debugging-порта наружу.

Chromium в этой конфигурации upstream запускает без browser sandbox (стандартный
режим bundled Chromium в контейнере). Изоляция профиля не является защитой от
враждебного сайта. Не использовать браузер с секретами или чувствительными
mounts для недоверенных страниц; при необходимости нужен отдельный контейнер.
Не путать browser automation с набором Playwright Test в прикладном проекте.

## Understand Anything

Навыки доступны как `/skill:understand`, `/skill:understand-dashboard`,
`/skill:understand-diff` и другие upstream-скиллы. Специализированные агенты
upstream установлены в `~/.pi/agent/agents/` для существующего `subagent`.
Полный анализ сам по себе не стартует; commit hooks не устанавливаются.
Первый анализ может расходовать много токенов.

Граф `.ua/` — производное описание текущего кода, не источник истины и не замена
Hindsight. В образе задано `UNDERSTAND_NO_WORKTREE_REDIRECT=1`, чтобы upstream не
перенаправлял запись из агентского worktree в основной checkout. Не анализировать
каталоги секретов; внимательно задавать scope и `.understandignore`.

Core собран заранее, dashboard использует установленный upstream runtime.
Версии меняются осознанно: npm — через `package.json` + lock, git — через ARG REF
в Dockerfile. Новые инструменты не обновляются неявно при запуске агента.
