#!/usr/bin/env python3
"""Selected agent storage: host preparation/migration and container links/launchers."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

import tomllib

AGENTS = ("claude", "codex", "pi")
CONFIG = {
    "claude": ("settings.json",),
    "codex": ("config.toml",),
    "pi": ("settings.json", "models-store.json"),
}
DATA_DIRS = {
    "claude": ("projects",),
    "codex": ("sessions", "archived_sessions", "memories"),
    "pi": ("sessions", "memory", "subagents"),
}
# Paths relative to the native agent home; all targets are in mounted directories.
FILES = {
    "claude": {
        "settings.json": "config/settings.json",
        ".credentials.json": "auth/credentials.json",
        "history.jsonl": "data/history.jsonl",
    },
    "codex": {
        "config.toml": "config/config.toml",
        "auth.json": "auth/auth.json",
        "history.jsonl": "data/history.jsonl",
        "session_index.jsonl": "data/session_index.jsonl",
    },
    "pi": {
        "settings.json": "config/settings.json",
        "models-store.json": "config/models-store.json",
        "auth.json": "auth/auth.json",
    },
}
CODEX_CONFIG = """cli_auth_credentials_store = "file"
[analytics]
enabled = false
[feedback]
enabled = false
[otel]
exporter = "none"
metrics_exporter = "none"
trace_exporter = "none"
"""


def host_root(home):
    return home / ".config/devenv/agents"


def runtime_root(home):
    return home / ".local/share/devenv/agents/codex/sqlite"


def native_home(home, agent):
    return home / {"claude": ".claude", "codex": ".codex", "pi": ".pi/agent"}[agent]


def make_dirs(home):
    root = host_root(home)
    for agent in AGENTS:
        for kind in ("config", "data", "auth"):
            (root / agent / kind).mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in DATA_DIRS[agent]:
            (root / agent / "data" / name).mkdir(parents=True, exist_ok=True)
    runtime_root(home).mkdir(parents=True, exist_ok=True, mode=0o700)
    (home / ".local/share/devenv/nix").mkdir(parents=True, exist_ok=True)
    auth = root / "pi/auth/auth.json"
    if not auth.exists():
        create_file(auth, "{}\n")


def create_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never truncate a concurrently created file.
    try:
        with path.open("x") as out:
            os.chmod(path, 0o600)
            out.write(text)
    except FileExistsError:
        pass


def validate_codex_config(path):
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    if "sqlite_home" in config:
        raise ValueError(
            f"Удалите sqlite_home из {path}: базы должны использовать "
            "локальный CODEX_SQLITE_HOME для snapshot/restore"
        )
    if config.get("cli_auth_credentials_store", "file") != "file":
        raise ValueError(
            f"{path}: для сохранения входа нужен "
            'cli_auth_credentials_store = "file" (не keyring/auto)'
        )


def require_config(root):
    for agent, names in CONFIG.items():
        for name in names:
            path = root / agent / "config" / name
            if not path.is_file() or path.is_symlink():
                raise ValueError(
                    f"Нужен обычный файл {path}; выполните migrate-agents "
                    "или дождитесь Syncthing"
                )
    validate_codex_config(root / "codex/config/config.toml")


def initialize(home):
    # Do not seed defaults on a second machine before synchronization arrives.
    require_config(host_root(home))
    make_dirs(home)


def migration_sources(home, dotfiles):
    root = host_root(home)
    pairs = []

    def add(source, agent, destination):
        pairs.append((source, root / agent / destination))

    for name in CONFIG["pi"]:
        add(home / ".config/devenv/pi" / name, "pi", "config/" + name)
    for name in DATA_DIRS["pi"]:
        add(home / ".pi/agent" / name, "pi", "data/" + name)
    add(home / ".pi/agent/auth.json", "pi", "auth/auth.json")
    add(home / ".claude/projects", "claude", "data/projects")
    add(home / ".claude/history.jsonl", "claude", "data/history.jsonl")
    add(home / ".claude/.credentials.json", "claude", "auth/credentials.json")
    add(home / ".config/devenv/claude.env", "claude", "auth/claude.env")
    # Prefer the actual user settings, falling back to local dotfiles only if absent.
    settings = home / ".claude/settings.json"
    if not settings.is_file() and dotfiles:
        settings = dotfiles / "claude/.claude/settings.json"
    add(settings, "claude", "config/settings.json")
    for base in (home / ".local/share/devenv/codex", home / ".codex"):
        for name in DATA_DIRS["codex"] + ("history.jsonl", "session_index.jsonl"):
            add(base / name, "codex", "data/" + name)
        add(base / "auth.json", "codex", "auth/auth.json")
        # Old snapshots/DBs are copied while stopped, never live-synced.
        for db in sorted(base.glob("*.sqlite*")) + sorted(
            (base / "sqlite").glob("*.sqlite*")
        ):
            pairs.append((db, runtime_root(home) / db.name))
    add(home / ".config/devenv/codex/config.toml", "codex", "config/config.toml")
    add(home / ".codex/config.toml", "codex", "config/config.toml")
    return pairs


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def migrate(home, dotfiles=None):
    """Preflight all conflicts before copying; originals remain untouched."""
    copies = {}
    for source, destination in migration_sources(home, dotfiles):
        if not source.exists():
            continue
        items = source.rglob("*") if source.is_dir() else [source]
        for item in items:
            if item.is_symlink() and item.is_dir():
                raise ValueError(f"Перенесите directory symlink вручную: {item}")
            if not item.is_file():
                continue
            target = (
                destination / item.relative_to(source)
                if source.is_dir()
                else destination
            )
            other = copies.get(target, target if target.exists() else None)
            if other and (
                item.stat().st_size != other.stat().st_size
                or digest(item) != digest(other)
            ):
                raise ValueError(
                    f"Конфликт: {item} и {other} -> {target}; "
                    "выберите актуальную версию вручную"
                )
            copies[target] = item
    for target, source in copies.items():
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive creation protects against a concurrent migration/sync write.
        with target.open("xb") as out, source.open("rb") as inp:
            os.chmod(target, 0o600)
            shutil.copyfileobj(inp, out)
    root = host_root(home)
    create_file(root / "claude/config/settings.json", "{}\n")
    create_file(root / "codex/config/config.toml", CODEX_CONFIG)
    initialize(home)


def atomic_copy(source, target):
    fd, temp = tempfile.mkstemp(prefix=".devenv-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_json(path, value):
    fd, temp = tempfile.mkstemp(prefix=".devenv-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def fingerprint(path):
    return digest(path) if path.is_file() else None


@contextmanager
def client_lock(home, agent):
    native = native_home(home, agent)
    native.mkdir(parents=True, exist_ok=True)
    with (native / ".devenv-client.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(
                f"{agent} уже запущен в этом контейнере; "
                "для параллельной задачи используйте другой контейнер"
            ) from exc
        yield


def reconcile(home, mounts, agent):
    """CAS publication: private credentials cannot resurrect an older login.

    Auth is private during a command. Config/data retain native symlinks, but
    atomically replaced files are published only if shared state is unchanged.
    A per-device lock + revisions (including logout tombstones) coordinate all
    containers. Conflicting files are preserved outside Syncthing in auth/.
    """
    native, base = native_home(home, agent), mounts / agent
    native.mkdir(parents=True, exist_ok=True)
    baseline_path = native / ".devenv-baselines.json"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.is_file() else {}
    metadata_path = base / "auth/.devenv-state.json"
    with (base / "auth/.devenv-storage.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        metadata = (
            json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
        )
        updated = {}
        for name, relative in FILES[agent].items():
            path, target = native / name, base / relative
            actual = fingerprint(target)
            state = metadata.get(name)
            if state is None or state["hash"] != actual:
                state = {
                    "revision": uuid.uuid4().hex,
                    "hash": actual,
                    "deleted": actual is None,
                }
            old = baseline.get(name)
            private = not path.is_symlink()
            local = fingerprint(path) if private else actual
            changed = old is not None and private and local != old["local"]
            is_auth = relative.startswith("auth/")
            if changed and local is None and is_auth:
                # Logout wins over concurrent refresh. Keep a new revision even
                # when the shared credential has already been removed.
                target.unlink(missing_ok=True)
                state = {"revision": uuid.uuid4().hex, "hash": None, "deleted": True}
            elif changed and local is not None and local != actual:
                if old["revision"] != state["revision"] or old["hash"] != actual:
                    conflict = base / "auth/conflicts"
                    conflict.mkdir(exist_ok=True, mode=0o700)
                    saved = conflict / (uuid.uuid4().hex + "-" + name.lstrip("."))
                    atomic_copy(path, saved)
                    print(
                        f"{agent}: устаревшее изменение {name} не опубликовано; "
                        f"копия сохранена в {saved}",
                        file=sys.stderr,
                    )
                else:
                    atomic_copy(path, target)
                    state = {
                        "revision": uuid.uuid4().hex,
                        "hash": local,
                        "deleted": False,
                    }
            elif old is None and relative.startswith("data/") and actual is None:
                create_file(target, "")
                state = {
                    "revision": uuid.uuid4().hex,
                    "hash": fingerprint(target),
                    "deleted": False,
                }
            if path.is_file() or path.is_symlink():
                path.unlink()
            if is_auth:
                # Never let a client mutate shared credentials behind the CAS
                # protocol. Two sessions may keep using their own access tokens,
                # but stale refresh results cannot overwrite a newer login.
                if target.is_file():
                    atomic_copy(target, path)
            else:
                path.symlink_to(target)
            metadata[name] = state
            updated[name] = {**state, "local": fingerprint(path)}
        write_json(metadata_path, metadata)
        write_json(baseline_path, updated)


def setup(home, mounts=Path("/run/agents")):
    for agent in AGENTS:
        base = mounts / agent
        if not base.is_dir():
            continue
        with client_lock(home, agent):
            # Recover replacements/deletions before relinking after a restart.
            recovering = (native_home(home, agent) / ".devenv-baselines.json").is_file()
            if recovering:
                reconcile(home, mounts, agent)
            for name in CONFIG[agent]:
                path = base / "config" / name
                if not path.is_file() or path.is_symlink():
                    raise ValueError(
                        f"Нет обычного файла {path}; проверьте конфигурацию на хосте"
                    )
            if agent == "codex":
                validate_codex_config(base / "config/config.toml")
            if not recovering:
                reconcile(home, mounts, agent)


def launch(home, mounts, agent, args, binary=None):
    binary = (
        binary
        or {
            "claude": home / ".local/bin/claude-native",
            "codex": Path("/usr/local/bin/codex"),
            "pi": Path("/usr/local/bin/pi"),
        }[agent]
    )
    if not (mounts / agent).is_dir():
        os.execv(str(binary), [str(binary), *args])
    with client_lock(home, agent):
        return run_client(home, mounts, agent, args, binary)


def run_client(home, mounts, agent, args, binary):
    reconcile(home, mounts, agent)
    if agent == "codex":
        validate_codex_config(mounts / agent / "config/config.toml")
    # Shared host inode: handoff tools refuse to snapshot/restore active Codex.
    lock = None
    if agent == "codex":
        runtime = Path(os.environ.get("CODEX_SQLITE_HOME", str(runtime_root(home))))
        runtime.mkdir(parents=True, exist_ok=True)
        lock = (runtime / ".devenv-active.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_SH)
    child = subprocess.Popen([str(binary), *args])
    # SIGINT is already delivered to the child in the foreground process group.
    signal.signal(signal.SIGINT, lambda *_: None)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda number, _frame: child.send_signal(number))
    try:
        code = child.wait()
    finally:
        try:
            reconcile(home, mounts, agent)
        finally:
            if lock is not None:
                lock.close()
    return code if code >= 0 else 128 - code


def sqlite_files(directory):
    return sorted(
        p for p in directory.glob("*.sqlite") if not p.name.startswith("logs_")
    )


def sqlite_backup(source, target):
    with (
        closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        ) as inp,
        closing(sqlite3.connect(str(target))) as out,
    ):
        inp.backup(out)
    os.chmod(target, 0o600)


def snapshot(home, restore=False):
    """Clean SQLite handoff; verify a complete snapshot set before restoring."""
    runtime = runtime_root(home)
    config = host_root(home) / "codex/config/config.toml"
    if config.is_file():
        validate_codex_config(config)
    snapshots = host_root(home) / "codex/data/sqlite-snapshot"
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (runtime / ".devenv-active.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(
                "Сначала завершите все клиенты Codex на этом устройстве"
            ) from exc
        if restore:
            restore_snapshot(runtime, snapshots)
        else:
            export_snapshot(runtime, snapshots)


def export_snapshot(runtime, snapshots):
    databases = sqlite_files(runtime)
    if not databases:
        print("Нет рабочих SQLite-баз Codex; существующие снимки не изменены")
        return
    snapshots.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Stage outside Syncthing and publish the manifest last. Checksums detect
    # out-of-order/partial sync before any local state is replaced.
    with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=runtime) as temp:
        staging = Path(temp)
        files = {}
        for db in databases:
            sqlite_backup(db, staging / db.name)
            files[db.name] = digest(staging / db.name)
        for name in files:
            atomic_copy(staging / name, snapshots / name)
        manifest = staging / "manifest.json"
        manifest.write_text(json.dumps({"version": 1, "files": files}, sort_keys=True))
        atomic_copy(manifest, snapshots / "manifest.json")
        for stale in sqlite_files(snapshots):
            if stale.name not in files:
                stale.unlink()


def restore_snapshot(runtime, snapshots):
    manifest = snapshots / "manifest.json"
    if not manifest.is_file():
        raise ValueError(
            f"Нет снимков SQLite (manifest.json) в {snapshots}; дождитесь синхронизации"
        )
    info = json.loads(manifest.read_text())
    if not isinstance(info, dict):
        raise ValueError("Некорректный manifest.json снимков SQLite")
    files = info.get("files")
    if info.get("version") != 1 or not isinstance(files, dict) or not files:
        raise ValueError("Некорректный manifest.json снимков SQLite")
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=runtime) as temp:
        staging = Path(temp)
        # Freeze inputs outside Syncthing before validation and replacement.
        for name in files:
            if (
                Path(name).name != name
                or not name.endswith(".sqlite")
                or name.startswith("logs_")
            ):
                raise ValueError(f"Недопустимое имя базы в manifest: {name}")
            source = snapshots / name
            if not source.is_file():
                raise ValueError(f"Снимок {name} ещё не синхронизирован или повреждён")
            atomic_copy(source, staging / name)
        apply_snapshot(runtime, staging, files)


def apply_snapshot(runtime, snapshots, files):
    # Check every input before modifying any local DB, including stale ones.
    for name, checksum in files.items():
        if (
            Path(name).name != name
            or not name.endswith(".sqlite")
            or name.startswith("logs_")
        ):
            raise ValueError(f"Недопустимое имя базы в manifest: {name}")
        source = snapshots / name
        if not source.is_file() or digest(source) != checksum:
            raise ValueError(f"Снимок {name} ещё не синхронизирован или повреждён")
        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        ) as conn:
            if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError(f"Повреждена SQLite-база {name}")
    local = sqlite_files(runtime)
    if local:
        backup = Path(tempfile.mkdtemp(prefix="before-restore-", dir=runtime))
        for db in local:
            sqlite_backup(db, backup / db.name)
    # Restore exactly the source set, not a mix of source + stale device state.
    for name in files:
        for suffix in ("-wal", "-shm"):
            (runtime / (name + suffix)).unlink(missing_ok=True)
        atomic_copy(snapshots / name, runtime / name)
    for stale in local:
        if stale.name not in files:
            for suffix in ("", "-wal", "-shm"):
                Path(str(stale) + suffix).unlink(missing_ok=True)


def main():
    # Preserve every argument and its order, including provider/client flags.
    if len(sys.argv) >= 3 and sys.argv[1] == "launch" and sys.argv[2] in AGENTS:
        try:
            return launch(Path.home(), Path("/run/agents"), sys.argv[2], sys.argv[3:])
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["init", "migrate", "setup", "launch", "snapshot", "restore"]
    )
    parser.add_argument("--dotfiles", type=Path)
    options = parser.parse_args()
    home = Path.home()
    try:
        if options.command == "init":
            initialize(home)
        elif options.command == "migrate":
            migrate(home, options.dotfiles)
        elif options.command == "setup":
            setup(home)
        elif options.command in ("snapshot", "restore"):
            snapshot(home, restore=options.command == "restore")
        elif options.command == "launch":
            parser.error("launch требует имя агента")
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
