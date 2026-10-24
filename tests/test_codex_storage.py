"""Launcher filesystem semantics for credentials and rename-based writes."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from test_pi_config import ROOT, storage


class AgentLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.mounts = self.root / 'mounts'
        for agent in storage.AGENTS:
            for kind in ('config', 'auth', 'data'):
                (self.mounts / agent / kind).mkdir(parents=True)
            for name in storage.CONFIG[agent]:
                (self.mounts / agent / 'config' / name).write_text(
                    '{}' if name.endswith('.json') else '')
        storage.setup(self.home, self.mounts)
        self.old_signals = {s: signal.getsignal(s) for s in
                            (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        self.addCleanup(self.restore_signals)

    def restore_signals(self):
        for number, handler in self.old_signals.items():
            signal.signal(number, handler)

    def launch(self, agent, body, args=()):
        fake = self.root / 'fake-client'
        fake.write_text('#!/bin/sh\n' + body)
        fake.chmod(0o755)
        old = os.environ.get('HOME')
        os.environ['HOME'] = str(self.home)
        try:
            return storage.launch(self.home, self.mounts, agent, list(args), binary=fake)
        finally:
            if old is None:
                os.environ.pop('HOME', None)
            else:
                os.environ['HOME'] = old

    def test_login_logout_login_for_every_agent(self):
        for agent in storage.AGENTS:
            auth_name, auth_relative = next((name, target) for name, target in
                                           storage.FILES[agent].items()
                                           if target.startswith('auth/'))
            native = storage.native_home(self.home, agent) / auth_name
            saved = self.mounts / agent / auth_relative
            self.assertEqual(self.launch(agent, f'printf token > "{native}"\n'), 0)
            self.assertEqual(saved.read_text(), 'token')
            if agent == 'pi':
                # Pi deletes the provider entry under its store lock, not the file.
                self.launch(agent, f'printf "{{}}" > "{native}"\n')
                self.assertEqual(saved.read_text(), '{}')
            else:
                self.launch(agent, f'rm "{native}"\n')
                self.assertFalse(saved.exists())
            self.launch(agent, f'printf new-token > "{native}"\n')
            self.assertEqual(saved.read_text(), 'new-token')

    def test_atomic_replacement_saved_on_nonzero_exit(self):
        self.assertEqual(self.launch('codex', '''printf index > "$HOME/.codex/index.new"
mv "$HOME/.codex/index.new" "$HOME/.codex/session_index.jsonl"
printf config > "$HOME/.codex/config.new"
mv "$HOME/.codex/config.new" "$HOME/.codex/config.toml"
exit 7
'''), 7)
        self.assertEqual((self.mounts / 'codex/data/session_index.jsonl').read_text(), 'index')
        self.assertEqual((self.mounts / 'codex/config/config.toml').read_text(), 'config')
        self.assertTrue((self.home / '.codex/session_index.jsonl').is_symlink())

    def test_pi_upgrade_preserves_private_auth_without_overwriting_shared(self):
        saved = self.mounts / 'pi/auth/auth.json'
        saved.write_text('current-shared-token')
        path = self.home / '.pi/agent/auth.json'
        path.unlink()
        path.write_text('private-token-from-old-container')
        self.launch('pi', 'exit 0\n')
        self.assertEqual(saved.read_text(), 'current-shared-token')
        self.assertTrue(path.is_symlink())
        copies = list((self.mounts / 'pi/auth/conflicts').iterdir())
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0].read_text(), 'private-token-from-old-container')
        self.assertNotIn('auth.json', json.loads(
            (self.home / '.pi/agent/.devenv-baselines.json').read_text()))

    def test_pi_shared_view_redirects_non_auth_resources(self):
        view = self.mounts / 'pi/auth/agent'
        self.assertEqual((view / 'auth.json').resolve(),
                         (self.mounts / 'pi/auth/auth.json').resolve())
        for name in (*storage.PI_VIEW_DIRS, *storage.PI_VIEW_FILES):
            self.assertEqual((view / name).readlink(), self.home / '.pi/agent' / name)
        # The lock's parent, not merely the credential's target, must be shared.
        lock = view / 'auth.json.lock'
        lock.mkdir()
        storage.reconcile(self.home, self.mounts, 'pi')
        self.assertTrue(lock.is_dir())

    def test_pi_launcher_uses_shared_agent_dir_even_with_inherited_override(self):
        with mock.patch.dict(os.environ, {'PI_CODING_AGENT_DIR': '/wrong'}):
            self.assertEqual(self.launch('pi', '''
[ "$PI_CODING_AGENT_DIR" = "''' + str(self.mounts / 'pi/auth/agent') + '''" ] || exit 8
printf refreshed > "$PI_CODING_AGENT_DIR/auth.json"
'''), 0)
        self.assertEqual((self.mounts / 'pi/auth/auth.json').read_text(), 'refreshed')

    def test_entrypoint_restart_keeps_replaced_credentials_and_logout(self):
        path = self.home / '.claude/.credentials.json'
        path.unlink(missing_ok=True)
        path.write_text('updated-before-restart')
        storage.setup(self.home, self.mounts)
        self.assertEqual((self.mounts / 'claude/auth/credentials.json').read_text(),
                         'updated-before-restart')
        path.unlink()
        storage.setup(self.home, self.mounts)
        self.assertFalse((self.mounts / 'claude/auth/credentials.json').exists())

    def test_overlapping_containers_cannot_resurrect_logout(self):
        for agent in ('claude', 'codex'):
            name, relative = next((n, r) for n, r in storage.FILES[agent].items()
                                  if r.startswith('auth/'))
            native_a = storage.native_home(self.home, agent) / name
            native_a.write_text('original-token')
            storage.reconcile(self.home, self.mounts, agent)
            other = self.root / ('container-b-' + agent)
            other.mkdir()
            storage.setup(other, self.mounts)
            native_b = storage.native_home(other, agent) / name
            # A refreshes privately while B logs out; A exits last.
            native_a.write_text('stale-refresh-from-a')
            native_b.unlink()
            storage.reconcile(other, self.mounts, agent)
            storage.reconcile(self.home, self.mounts, agent)
            self.assertFalse((self.mounts / agent / relative).exists())
            self.assertFalse(native_a.exists())
            conflicts = list((self.mounts / agent / 'auth/conflicts').iterdir())
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].read_text(), 'stale-refresh-from-a')

    def test_real_overlapping_launchers_cannot_undo_logout(self):
        native_a = self.home / '.codex/auth.json'
        native_a.write_text('original')
        storage.reconcile(self.home, self.mounts, 'codex')
        other = self.root / 'container-b'
        other.mkdir()
        storage.setup(other, self.mounts)
        ready, finish = self.root / 'ready', self.root / 'finish'
        client_a = self.root / 'client-a'
        client_a.write_text('#!/bin/sh\nprintf refreshed > "$1/.codex/auth.json"\n'
                            'touch "$2"\nwhile [ ! -e "$3" ]; do sleep 0.02; done\n')
        client_b = self.root / 'client-b'
        client_b.write_text('#!/bin/sh\nrm "$1/.codex/auth.json"\n')
        client_a.chmod(0o755)
        client_b.chmod(0o755)
        runner = '''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('s', sys.argv[1]); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
sys.exit(s.launch(Path(sys.argv[2]),Path(sys.argv[3]),'codex',sys.argv[5:],binary=Path(sys.argv[4])))
'''
        args = [sys.executable, '-c', runner, str(ROOT / 'scripts/agent_storage.py')]
        process = subprocess.Popen(args + [str(self.home), str(self.mounts), str(client_a),
                                          str(self.home), str(ready), str(finish)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists(), 'launcher A did not start')
            subprocess.run(args + [str(other), str(self.mounts), str(client_b), str(other)],
                           check=True, capture_output=True, text=True, timeout=10)
            self.assertFalse((self.mounts / 'codex/auth/auth.json').exists())
            finish.touch()
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
            self.assertIn('не опубликовано', error)
            self.assertFalse((self.mounts / 'codex/auth/auth.json').exists())
        finally:
            finish.touch()
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=10)

    def test_overlapping_logins_keep_the_newer_published_credentials(self):
        agent = 'codex'
        path_a = self.home / '.codex/auth.json'
        path_a.write_text('original')
        storage.reconcile(self.home, self.mounts, agent)
        other = self.root / 'container-b'
        other.mkdir()
        storage.setup(other, self.mounts)
        path_a.write_text('refresh-a')
        (other / '.codex/auth.json').write_text('login-b')
        storage.reconcile(other, self.mounts, agent)
        storage.reconcile(self.home, self.mounts, agent)
        self.assertEqual((self.mounts / 'codex/auth/auth.json').read_text(), 'login-b')
        self.assertEqual(path_a.read_text(), 'login-b')

    def test_concurrent_index_replacements_preserve_conflicts(self):
        other = self.root / 'container-b'
        other.mkdir()
        storage.setup(other, self.mounts)
        for home, content in ((self.home, 'index-a'), (other, 'index-b')):
            path = home / '.codex/session_index.jsonl'
            path.unlink()
            path.write_text(content)
        storage.reconcile(other, self.mounts, 'codex')
        storage.reconcile(self.home, self.mounts, 'codex')
        self.assertEqual((self.mounts / 'codex/data/session_index.jsonl').read_text(), 'index-b')
        self.assertEqual(next((self.mounts / 'codex/auth/conflicts').iterdir()).read_text(), 'index-a')

    def test_same_container_rejects_two_sessions_sharing_native_files(self):
        for agent in ('claude', 'codex'):
            with storage.client_lock(self.home, agent):
                with self.assertRaisesRegex(ValueError, 'уже запущен'):
                    self.launch(agent, 'exit 0\n')

    def test_native_argv_is_preserved(self):
        output = self.root / 'argv.json'
        client = self.root / 'capture.py'
        client.write_text(f'#!{sys.executable}\nimport json,sys\n'
                          f'open({str(output)!r}, "w").write(json.dumps(sys.argv[1:]))\n')
        client.chmod(0o755)
        args = ['--model', 'a/b', 'hello world', '--dotfiles', '/not-a-storage-option']
        self.assertEqual(storage.launch(self.home, self.mounts, 'pi', args, binary=client), 0)
        self.assertEqual(json.loads(output.read_text()), args)

    def test_cli_dispatch_does_not_parse_client_flags(self):
        # Invoke the real CLI, replacing only the launch implementation in-process.
        code = '''import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('s', sys.argv[1]); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
s.launch=lambda home,mounts,agent,args: print(json.dumps([agent,args])) or 0
sys.argv=['storage','launch','codex','--model','test','--dotfiles','literal','prompt']
s.main()
'''
        result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts/agent_storage.py')],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout),
                         ['codex', ['--model', 'test', '--dotfiles', 'literal', 'prompt']])
