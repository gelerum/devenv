#!/usr/bin/env python3
"""Shared Jupyter IDE, with exactly one kernel from the selected project venv."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.request import ProxyHandler, Request, build_opener

TOOLS = Path('/opt/jupyter/.venv')


def project_root(directory):
    directory = Path(directory).resolve()
    result = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=directory,
                            capture_output=True, text=True)
    return Path(result.stdout.strip()) if result.returncode == 0 else directory


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.jupyter-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_kernel(python):
    # Do not resolve this symlink: /project/.venv/bin/python must retain its
    # venv identity, even when the executable points to /usr/bin/python3.12.
    if not python.is_file():
        raise ValueError(f'Project Python missing: {python}; run uv sync --locked first')
    result = subprocess.run([
        str(python), '-I', '-c',
        'import importlib.util,json,sys; '
        'print(json.dumps({"prefix":sys.prefix,"kernel":importlib.util.find_spec("ipykernel") is not None}))',
    ], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError('Project Python failed its isolated ipykernel probe')
    probe = json.loads(result.stdout)
    if not probe['kernel']:
        raise ValueError('ipykernel missing in project Python; run uv sync --locked (including dev group)')
    return probe['prefix']


def prepare(root, python, tools, state, port, ip='0.0.0.0', prefix=None):
    for binary in ('jupyter-lab', 'basedpyright-langserver', 'ruff'):
        if not (tools / 'bin' / binary).is_file():
            raise ValueError(f'Jupyter IDE tool missing: {binary}; rebuild devenv image')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    kernel = 'project-' + hashlib.sha256(str(root).encode()).hexdigest()[:16]
    settings = state / 'settings'
    kernels = state / 'data/kernels'
    for directory in (state / 'config', state / 'runtime', settings, state / 'workspaces'):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(kernels / kernel / 'kernel.json', {
        'argv': [str(python), '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        'display_name': f'Python ({root.name})', 'language': 'python',
        'env': {'VIRTUAL_ENV': prefix or str(python.parent.parent),
                'PATH': str(python.parent) + os.pathsep + os.environ.get('PATH', ''),
                'PYTHONPATH': '', 'PYTHONHOME': ''},
    })
    write_json(settings / '@jupyter-lsp/jupyterlab-lsp/plugin.jupyterlab-settings', {
        'language_servers': {'basedpyright': {'priority': 100, 'serverSettings': {
            'python.pythonPath': str(python),
            'basedpyright.analysis.typeCheckingMode': 'standard',
        }}},
    })
    # Follow the browser's system color scheme; seed defaults only so a later
    # explicit choice in Settings survives server restarts.
    theme_settings = settings / '@jupyterlab/apputils-extension/themes.jupyterlab-settings'
    if not theme_settings.exists():
        write_json(theme_settings, {
            'theme': 'Catppuccin Latte',
            'adaptive-theme': True,
            'preferred-light-theme': 'Catppuccin Latte',
            'preferred-dark-theme': 'Catppuccin Mocha',
        })
    # Match Ghostty's JetBrainsMono Nerd Font at 12 pt (16 CSS px at 96 dpi).
    # CodeMirror defaults apply to both notebook cells and file editors.
    editor_settings = settings / '@jupyterlab/codemirror-extension/plugin.jupyterlab-settings'
    if not editor_settings.exists():
        write_json(editor_settings, {
            'defaultConfig': {'customStyles': {
                'fontFamily': '"JetBrainsMono Nerd Font", monospace',
                'fontSize': 16,
            }},
        })
    config_args = []
    pyproject = root / 'pyproject.toml'
    if pyproject.is_file() and 'ruff' in tomllib.loads(pyproject.read_text()).get('tool', {}):
        config_args = ['--config', str(pyproject)]
    elif (root / 'ruff.toml').is_file():
        config_args = ['--config', str(root / 'ruff.toml')]
    elif (root / '.ruff.toml').is_file():
        config_args = ['--config', str(root / '.ruff.toml')]
    write_json(settings / 'jupyterlab_code_formatter/settings.jupyterlab-settings', {
        'preferences': {'default_formatter': {'python': ['ruff', 'ruffformat']}},
        'ruff': {'args': [*config_args, '--select=I001']},
        'ruffformat': {'args': config_args},
        'formatOnSave': True,
    })
    config = state / 'config/jupyter_server_config.json'
    write_json(config, {
        'ServerApp': {'ip': ip, 'port': port, 'port_retries': 0,
                      'open_browser': False, 'root_dir': str(root)},
        'IdentityProvider': {'token': secrets.token_urlsafe(32)},
        'KernelSpecManager': {'ensure_native_kernel': False,
                              'allowed_kernelspecs': [kernel]},
        'MappingKernelManager': {'default_kernel_name': kernel},
        'LabApp': {'user_settings_dir': str(settings),
                   'workspaces_dir': str(state / 'workspaces')},
        'LanguageServerManager': {
            'autodetect': False,
            'language_servers': {'basedpyright': {
                'version': 2,
                'argv': [str(tools / 'bin/basedpyright-langserver'), '--stdio'],
                'languages': ['python'],
                'mime_types': ['text/x-python', 'text/x-ipython'],
                'display_name': 'basedpyright (project Python)',
            }},
        },
    })
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    # kernel_dirs is not a configurable trait in current jupyter-client.
    # Use its supported data-path mechanism; the allowlist hides all other
    # discovered specs, including the tool environment's own Python kernel.
    env.update(JUPYTER_PATH=str(state / 'data'),
               JUPYTER_CONFIG_DIR=str(state / 'config'),
               JUPYTER_RUNTIME_DIR=str(state / 'runtime'),
               JUPYTERLAB_SETTINGS_DIR=str(settings),
               JUPYTERLAB_WORKSPACES_DIR=str(state / 'workspaces'),
               PATH=str(tools / 'bin') + os.pathsep + env.get('PATH', ''))
    # Explicit IdentityProvider token wins over an accidentally inherited empty
    # JUPYTER_TOKEN, and config lives in private cache, never in project Git.
    env.pop('JUPYTER_TOKEN', None)
    env.pop('JUPYTER_TOKEN_FILE', None)
    return [str(tools / 'bin/jupyter-lab'), '--config', str(config)], env


def server_info(state):
    for path in sorted((state / 'runtime').glob('jpserver-*.json')):
        try:
            info = json.loads(path.read_text())
            os.kill(info['pid'], 0)
            request = Request(f'http://127.0.0.1:{info["port"]}/api/status',
                              headers={'Authorization': 'token ' + info['token']})
            # Cache is persistent but PIDs are container-local and can be reused.
            # Confirm an authenticated live server before trusting a stale file.
            with build_opener(ProxyHandler({})).open(request, timeout=1) as response:
                if response.status == 200:
                    return info
        except (OSError, ValueError, KeyError):
            continue
    return None


def process_identity(pid):
    # PID alone is unsafe in a persistent cache across container restarts.
    # Linux start ticks + host boot ID distinguish reused container-local PIDs.
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'pid': pid, 'start': fields[19],
                'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError):
        return None


def pending_process(state):
    try:
        saved = json.loads((state / 'process.json').read_text())
        if saved == process_identity(saved['pid']):
            return saved
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--python', type=Path, help='Kernel interpreter; default PROJECT/.venv/bin/python')
    parser.add_argument('--tools', type=Path, default=TOOLS, help=argparse.SUPPRESS)
    parser.add_argument('--state-base', type=Path,
                        default=Path.home() / '.cache/devenv/jupyter', help=argparse.SUPPRESS)
    parser.add_argument('--port', type=int, default=8888, help='Container port, not published host port')
    parser.add_argument('--ip', default='0.0.0.0', help='Container listener; publish host loopback only')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Validate tools/kernel, prepare config; do not start')
    mode.add_argument('--detach', action='store_true', help='Start independent of terminal; logs in private cache')
    mode.add_argument('--status', action='store_true', help='Show status without printing token')
    mode.add_argument('--url', action='store_true', help='Print login URL (contains a secret token)')
    mode.add_argument('--stop', action='store_true', help='Request shutdown of this project server/kernels')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be 1..65535')
    root = project_root(args.project)
    python = args.python.absolute() if args.python else root / '.venv/bin/python'
    key = hashlib.sha256(f'{root}:{args.port}'.encode()).hexdigest()[:24]
    state = args.state_base / key
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    with (state / 'launcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        info = server_info(state)
        pending = pending_process(state)
        if args.status or args.url or args.stop:
            if not info:
                if pending and args.status:
                    print(json.dumps({'project': str(root), 'port': args.port,
                                      'pid': pending['pid'], 'state': 'starting-or-unresponsive',
                                      'log': str(state / 'server.log')}))
                    return
                if pending:
                    raise ValueError(f'Jupyter process is alive but HTTP is not ready; inspect {state / "server.log"}')
                raise ValueError('No running Jupyter server for this project/port')
            if args.url:
                host_port = int(os.environ.get('DEVENV_JUPYTER_HOST_PORT', args.port))
                print(f'http://127.0.0.1:{host_port}/lab?token={info["token"]}')
            elif args.stop:
                request = Request(f'http://127.0.0.1:{info["port"]}/api/shutdown', data=b'{}',
                                  headers={'Authorization': 'token ' + info['token']})
                with build_opener(ProxyHandler({})).open(request, timeout=10):
                    pass
                print('Jupyter shutdown requested; kernels will stop')
            else:
                print(json.dumps({'project': str(root), 'port': info['port'], 'pid': info['pid'],
                                  'log': str(state / 'server.log')}))
            return
        if info or pending:
            raise ValueError('Jupyter is already running or starting for this project; use --status/--url or --stop')
        prefix = validate_kernel(python)
        cmd, env = prepare(root, python, args.tools, state, args.port, args.ip, prefix)
        if args.check:
            print(json.dumps({'project': str(root), 'python': str(python), 'state': str(state)}))
            return
        if args.detach:
            with (state / 'server.log').open('ab') as log:
                os.chmod(log.name, 0o600)
                process = subprocess.Popen(cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            identity = process_identity(process.pid)
            if identity is None:
                raise ValueError(f'Jupyter startup failed; inspect {state / "server.log"}')
            # Publish before releasing launcher.lock, even when HTTP startup
            # exceeds our readiness wait. Last-shell cleanup must preserve it.
            write_json(state / 'process.json', identity)
            for _ in range(100):
                if process.poll() is not None:
                    raise ValueError(f'Jupyter startup failed; inspect {state / "server.log"}')
                if server_info(state):
                    print(f'Jupyter started for {root.name}; use devenv-jupyter --url for login')
                    return
                time.sleep(0.1)
            print(f'Jupyter is starting; inspect {state / "server.log"}')
            return
        # The server does not need the startup lock. CLOEXEC prevents the lock
        # being inherited after exec, and subsequent --status/--stop can work.
        os.chdir(root)
        os.execve(cmd[0], cmd, env)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(str(exc))
