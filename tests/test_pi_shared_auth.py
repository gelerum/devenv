"""Shared Pi store regressions; optional real CLI checks use DEVENV_TEST_PI_BINARY."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from test_pi_config import ROOT, storage


class PiSharedAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mounts = self.root / 'mounts'
        self.base = self.mounts / 'pi'
        for kind in ('config', 'auth', 'data'):
            (self.base / kind).mkdir(parents=True)
        for name in storage.CONFIG['pi']:
            (self.base / 'config' / name).write_text(
                '{"providers": {}}' if name == 'models.json' else '{}')
        self.shared = self.base / 'auth/auth.json'
        self.shared.write_text('{}')
        self.home = self.root / 'home'
        storage.setup(self.home, self.mounts)

    def test_trust_remains_native_and_existing_decisions_survive(self):
        native_a = self.home / '.pi/agent/trust.json'
        native_a.write_text('{"/workspace": true}')
        storage.setup(self.home, self.mounts)
        view_trust = self.base / 'auth/agent/trust.json'
        self.assertEqual(view_trust.readlink(), native_a)
        self.assertEqual(json.loads(view_trust.read_text()), {'/workspace': True})
        other = self.root / 'other'
        native_b = other / '.pi/agent/trust.json'
        native_b.parent.mkdir(parents=True)
        native_b.write_text('{"/workspace": false}')
        storage.setup(other, self.mounts)
        # In real containers the symlink has the same /home/q/... pathname,
        # resolving within each container's filesystem, never to host trust.
        self.assertEqual(view_trust.readlink(), native_b)
        self.assertEqual(json.loads(view_trust.read_text()), {'/workspace': False})
        view_trust.write_text('{"/workspace": null}')
        self.assertEqual(json.loads(native_a.read_text()), {'/workspace': True})

    def test_custom_native_relative_package_and_resource_paths_survive(self):
        native = self.home / '.pi/agent'
        package = native / 'custom-package'
        package.mkdir()
        (package / 'package.json').write_text('{"name": "test-package"}')
        (native / 'custom-extension.ts').write_text('// test extension')
        settings = {'packages': [{'source': './custom-package'}],
                    'extensions': ['./custom-extension.ts']}
        (self.base / 'config/settings.json').write_text(json.dumps(settings))
        storage.setup(self.home, self.mounts)
        view = self.base / 'auth/agent'
        for relative in ('custom-package/package.json', 'custom-extension.ts'):
            self.assertEqual((view / relative).read_bytes(), (native / relative).read_bytes())
        self.assertFalse((view / '.devenv-baselines.json').exists())

    def test_relative_resources_outside_native_dir_require_explicit_absolute_path(self):
        (self.base / 'config/settings.json').write_text(
            '{"packages": ["../outside-package"]}')
        with self.assertRaisesRegex(ValueError, 'абсолютным native-путём'):
            storage.setup(self.home, self.mounts)

    def test_old_exclusive_launcher_blocks_upgrade_without_touching_auth(self):
        native = self.home / '.pi/agent/auth.json'
        native.unlink()
        native.write_text('private-token-in-running-old-client')
        with storage.client_lock(self.home, 'pi'):
            with self.assertRaisesRegex(ValueError, 'старый лаунчер'):
                storage.setup(self.home, self.mounts)
            with self.assertRaisesRegex(ValueError, 'старый лаунчер'):
                storage.launch(self.home, self.mounts, 'pi', [], binary=Path('/bin/true'))
        self.assertFalse(native.is_symlink())
        self.assertEqual(native.read_text(), 'private-token-in-running-old-client')
        self.assertEqual(self.shared.read_text(), '{}')

    def test_new_shared_guard_allows_new_clients_but_prevents_old_launcher(self):
        with storage.client_lock(self.home, 'pi', shared=True):
            with storage.client_lock(self.home, 'pi', shared=True):
                with self.assertRaisesRegex(ValueError, 'уже запущен'):
                    with storage.client_lock(self.home, 'pi'):
                        self.fail('old exclusive launcher acquired lock')

    def test_live_clients_see_refresh_and_logout_without_reconcile(self):
        other = self.root / 'other'
        storage.setup(other, self.mounts)
        a = self.home / '.pi/agent/auth.json'
        b = other / '.pi/agent/auth.json'
        view_auth = self.base / 'auth/agent/auth.json'
        a.write_text('refreshed-in-a')
        self.assertEqual(b.read_text(), 'refreshed-in-a')
        self.assertEqual(view_auth.read_text(), 'refreshed-in-a')
        b.write_text('{}')
        self.assertEqual(a.read_text(), '{}')
        # Exiting either launcher must not resurrect the previous credential.
        storage.reconcile(self.home, self.mounts, 'pi')
        storage.reconcile(other, self.mounts, 'pi')
        self.assertEqual(self.shared.read_text(), '{}')

    def test_shared_store_replacement_is_visible(self):
        replacement = self.base / 'auth/new.json'
        replacement.write_text('new-login')
        replacement.replace(self.shared)
        self.assertEqual((self.home / '.pi/agent/auth.json').read_text(), 'new-login')
        self.assertEqual((self.base / 'auth/agent/auth.json').read_text(), 'new-login')

    def test_same_container_can_run_two_pi_launchers(self):
        client = self.root / 'fake-pi'
        client.write_text('#!/bin/sh\ntouch "$1"\n'
                          'while [ ! -e "$2" ]; do sleep 0.02; done\n')
        client.chmod(0o755)
        finish = self.root / 'finish'
        ready = [self.root / 'ready-a', self.root / 'ready-b']
        runner = '''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('s',sys.argv[1])
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
sys.exit(s.launch(Path(sys.argv[2]),Path(sys.argv[3]),'pi',sys.argv[5:],binary=Path(sys.argv[4])))
'''
        processes = []
        try:
            for marker in ready:
                processes.append(subprocess.Popen(
                    [sys.executable, '-c', runner, str(ROOT / 'scripts/agent_storage.py'),
                     str(self.home), str(self.mounts), str(client), str(marker), str(finish)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            deadline = time.monotonic() + 10
            while not all(p.exists() for p in ready) and time.monotonic() < deadline:
                if any(p.poll() is not None for p in processes):
                    break
                time.sleep(0.02)
            self.assertTrue(all(p.exists() for p in ready), 'second Pi did not start')
            finish.touch()
            for process in processes:
                out, err = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, err + out)
        finally:
            finish.touch()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=10)

    @unittest.skipUnless(os.environ.get('DEVENV_TEST_PI_BINARY'),
                         'set DEVENV_TEST_PI_BINARY for real Pi lock integration')
    def test_real_pi_processes_wait_for_same_shared_auth_lock(self):
        other = self.root / 'other'
        storage.setup(other, self.mounts)
        view = self.base / 'auth/agent'
        lock = view / 'auth.json.lock'
        lock.mkdir()
        runner = '''import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('s',sys.argv[1])
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
sys.exit(s.launch(Path(sys.argv[2]),Path(sys.argv[3]),'pi',
 ['auth','check','--provider','openai','--json'],binary=Path(sys.argv[4])))
'''
        args = [sys.executable, '-c', runner, str(ROOT / 'scripts/agent_storage.py')]
        env = {'PATH': os.environ['PATH'], 'PI_OFFLINE': '1', 'PI_TELEMETRY': '0'}
        processes = []
        try:
            for home in (self.home, self.home, other):
                processes.append(subprocess.Popen(
                    args + [str(home), str(self.mounts), os.environ['DEVENV_TEST_PI_BINARY']],
                    env={**env, 'HOME': str(home)}, cwd=home,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            # Each Pi must wait rather than read with a container-private lock.
            time.sleep(2)
            for process in processes:
                self.assertIsNone(process.poll(), 'Pi bypassed the shared auth lock')
            self.shared.write_text(json.dumps({'openai': {
                'type': 'oauth', 'access': 'fake-test-access',
                'refresh': 'fake-test-refresh', 'expires': 9999999999999,
            }}))
            lock.rmdir()
            for process in processes:
                out, err = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, err + out)
                self.assertEqual(json.loads(out)['status'], 'ready')
                self.assertNotIn('fake-test-access', out)
        finally:
            if lock.is_dir():
                lock.rmdir()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=10)
