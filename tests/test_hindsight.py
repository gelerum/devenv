import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('storage_hindsight', ROOT / 'scripts/agent_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


class HindsightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home, self.mounts, self.runtime = (self.root / name for name in ('home', 'mounts', 'runtime'))
        self.base = self.mounts / 'pi'
        for name in ('config', 'auth', 'data'):
            (self.base / name).mkdir(parents=True)
        self.put('config/settings.json', {'defaultModel': 'keep', 'extensions': ['/other.ts']})
        self.config = json.loads((ROOT / 'config/hindsight.example.json').read_text())
        for relative in ('.hindsight/coding-agents/dist/pi.js', '.pi/agent/skills/hindsight-coding-agent/SKILL.md'):
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('test')
        (self.base / 'auth/hindsight-api-key').write_text('a' * 64 + '\n')

    def put(self, relative, value):
        (self.base / relative).write_text(json.dumps(value))

    def prepare(self):
        return storage.prepare_hindsight(self.home, self.mounts, self.runtime)

    def test_disabled_by_default(self):
        self.assertEqual(self.prepare(), {})
        self.assertFalse((self.base / 'auth/hindsight-runtime.json').exists())

    def test_private_config_and_resources_survive_recreation(self):
        self.put('config/hindsight.json', self.config)
        native = self.home / '.pi/agent/settings.json'
        native.parent.mkdir(parents=True)
        native.symlink_to(self.base / 'config/settings.json')
        first = self.prepare()
        self.assertEqual(first, self.prepare())
        self.assertEqual(first['PI_MEMORY'], '0')
        settings = json.loads(native.read_text())
        self.assertEqual(settings['defaultModel'], 'keep')
        self.assertEqual(settings['extensions'][0], '/other.ts')
        self.assertEqual(len(settings['extensions']), 2)
        self.assertTrue(native.is_symlink())
        private = Path(first['HINDSIGHT_CONFIG'])
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(private.read_text())['apiToken'], 'a' * 64)
        self.assertNotIn('a' * 64, (self.base / 'config/hindsight.json').read_text())
        self.assertNotIn('a' * 64, native.read_text())

    def test_disable_restores_other_resources(self):
        self.put('config/hindsight.json', self.config)
        self.prepare()
        self.put('config/hindsight.json', {'enabled': False})
        self.assertEqual(self.prepare(), {})
        self.assertEqual(json.loads((self.base / 'config/settings.json').read_text())['extensions'], ['/other.ts'])

    def test_fail_closed_on_missing_secret_or_implicit_cloud(self):
        self.put('config/hindsight.json', self.config)
        (self.base / 'auth/hindsight-api-key').unlink()
        with self.assertRaisesRegex(ValueError, 'local'):
            self.prepare()
        self.config['apiUrl'] = ''
        self.put('config/hindsight.json', self.config)
        with self.assertRaisesRegex(ValueError, 'apiUrl'):
            self.prepare()

    def test_reject_synced_secret_and_missing_optin(self):
        for extra in ({'harnesses': {'pi': {'apiToken': 'bad'}}}, {'optInOnly': False}):
            self.put('config/hindsight.json', {**self.config, **extra})
            with self.assertRaises(ValueError):
                self.prepare()

    def test_reject_policy_overrides_and_ambiguous_mapping(self):
        for extra in (
            {'harnesses': {'pi': {'optInOnly': False}}},
            {'paths': {'/other': {'apiUrl': 'https://other.invalid'}}},
            {'banks': {'dev-infra': {'serverMode': 'cloud'}}},
            {'optInOnly': 'false'}, {'mapPathToBank': ['dev-infra']},
            {'mapPathToBank': {'relative': 'dev-infra'}},
            {'optInPaths': ['/other']},
            {'apiUrl': 'http://user:password@example.invalid'},
            {'apiUrl': 'http://'}, {'apiUrl': 'https://example.invalid?apiKey=secret'},
        ):
            with self.subTest(extra=extra):
                self.put('config/hindsight.json', {**self.config, **extra})
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_launcher_drops_inherited_hindsight_policy(self):
        with patch.object(storage, 'reconcile'), patch.object(storage, 'prepare_hindsight', return_value={
            'HINDSIGHT_CONFIG': '/private/config.json', 'PI_MEMORY': '0',
        }), patch.object(storage.subprocess, 'Popen') as child, patch.object(storage.signal, 'signal'), patch.dict(os.environ, {
            'HINDSIGHT_OPT_IN_PATHS': '/other', 'HINDSIGHT_API_URL': 'https://other.invalid',
            'HINDSIGHT_CONFIG': '/inherited/config.json',
        }):
            child.return_value.wait.return_value = 0
            self.assertEqual(storage.run_client(self.home, self.mounts, 'pi', [], '/pi'), 0)
            env = child.call_args.kwargs['env']
            self.assertNotIn('HINDSIGHT_OPT_IN_PATHS', env)
            self.assertNotIn('HINDSIGHT_API_URL', env)
            self.assertEqual(env['HINDSIGHT_CONFIG'], '/private/config.json')


if __name__ == '__main__':
    unittest.main()
