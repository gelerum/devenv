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

    def prepare(self, cwd=None):
        return storage.prepare_hindsight(self.home, self.mounts, self.runtime, cwd=cwd or self.root)

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
        self.assertNotIn(str(self.runtime / '.pi/agent/skills/hindsight-coding-agent'),
                         settings.get('skills', []))
        companion = self.home / '.pi/agent/skills/hindsight-coding-agent/SKILL.md'
        self.assertEqual(companion.read_text(), 'test')
        self.assertTrue(native.is_symlink())
        private = Path(first['HINDSIGHT_CONFIG'])
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)
        resolved = json.loads(private.read_text())
        self.assertEqual(resolved['apiToken'], 'a' * 64)
        self.assertEqual(resolved['autoInject'], 'none')
        self.assertTrue(resolved['retainSessions'])
        self.assertEqual(resolved['pageTriggerType'], 'cron')
        self.assertEqual(resolved['bankId'], storage.hindsight_project(self.root)[1])
        self.assertEqual(resolved['mapPathToBank'], {str(self.root): resolved['bankId']})
        self.assertTrue(resolved['optInOnly'])
        self.assertFalse(resolved['dynamicBankId'])
        self.assertNotIn('bankMode', resolved)
        self.assertNotIn('a' * 64, (self.base / 'config/hindsight.json').read_text())
        self.assertNotIn('a' * 64, native.read_text())

    def test_legacy_config_gets_scoped_memory_guidance_without_changing_synced_config(self):
        self.config.pop('toolGuideExtra')
        self.config.pop('pageRefreshEveryTurns')
        self.put('config/hindsight.json', self.config)
        private = Path(self.prepare()['HINDSIGHT_CONFIG'])
        resolved = json.loads(private.read_text())
        self.assertEqual(resolved['toolGuideExtra'], storage.HINDSIGHT_TASK_GUIDANCE)
        self.assertEqual(resolved['pageRefreshEveryTurns'], 10)
        self.assertEqual(resolved['autoInject'], 'none')
        self.assertTrue(resolved['retainSessions'])
        synced = json.loads((self.base / 'config/hindsight.json').read_text())
        self.assertNotIn('toolGuideExtra', synced)
        self.assertNotIn('pageRefreshEveryTurns', synced)

    def test_explicit_memory_guidance_and_refresh_cadence_are_preserved(self):
        self.config.update(toolGuideExtra='Custom user policy', pageRefreshEveryTurns=4)
        self.put('config/hindsight.json', self.config)
        resolved = json.loads(Path(self.prepare()['HINDSIGHT_CONFIG']).read_text())
        self.assertEqual(resolved['toolGuideExtra'], 'Custom user policy')
        self.assertEqual(resolved['pageRefreshEveryTurns'], 4)

    def test_example_limits_mechanical_searches_but_preserves_explicit_memory_requests(self):
        self.assertEqual(self.config['toolGuideExtra'], storage.HINDSIGHT_TASK_GUIDANCE)
        self.assertIn('purely mechanical requests', self.config['toolGuideExtra'])
        self.assertIn('Respect explicit requests to use memory', self.config['toolGuideExtra'])
        self.assertIn('page-roster refresh is not itself a reason', self.config['toolGuideExtra'])
        self.assertEqual(self.config['autoInject'], 'none')
        self.assertTrue(self.config['retainSessions'])

    def test_companion_skill_migration_removes_only_duplicate_registration(self):
        skill = str(self.runtime / '.pi/agent/skills/hindsight-coding-agent')
        self.put('config/settings.json', {'extensions': ['/other.ts'],
                                         'skills': ['/other-skill', skill]})
        self.put('config/hindsight.json', self.config)
        companion = self.home / '.pi/agent/skills/hindsight-coding-agent'
        companion.mkdir(parents=True)
        (companion / 'SKILL.md').write_text('old upstream copy')
        self.prepare()
        self.prepare()
        settings = json.loads((self.base / 'config/settings.json').read_text())
        self.assertEqual(settings['skills'], ['/other-skill'])
        self.assertEqual((companion / 'SKILL.md').read_text(), 'test')
        self.assertEqual(settings['extensions'].count(
            str(self.runtime / '.hindsight/coding-agents/dist/pi.js')), 1)

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

    def git(self, cwd, *args):
        result = storage.subprocess.run(['git', *args], cwd=cwd, text=True,
                                        capture_output=True, check=True)
        return result.stdout.strip()

    def test_path_slug_matches_legacy_memory(self):
        project = self.root / '2_Code' / 'Alpha_Бета.test'
        project.mkdir(parents=True)
        root, bank = storage.hindsight_project(project)
        self.assertEqual(root, project)
        self.assertEqual(bank, storage.re.sub(r'[^a-zA-Z0-9]', '-', str(project)))
        self.assertTrue(bank.endswith('-2-Code-Alpha------test'))

    def test_repo_subdirectory_and_worktree_share_main_bank(self):
        repo = self.root / 'repo'
        repo.mkdir()
        self.git(repo, 'init')
        self.git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '-m', 'initial')
        subdir = repo / 'src' / 'nested'
        subdir.mkdir(parents=True)
        worktree = self.root / 'other-worktree'
        self.git(repo, 'worktree', 'add', '-b', 'test-worktree', str(worktree))
        expected = storage.hindsight_project(repo)
        self.assertEqual(storage.hindsight_project(subdir), expected)
        self.assertEqual(storage.hindsight_project(worktree), expected)

    def test_non_bmp_slug_uses_javascript_utf16_semantics(self):
        project = self.root / 'emoji-😀'
        project.mkdir()
        self.assertTrue(storage.hindsight_project(project)[1].endswith('-emoji---'))

    def test_separate_git_dir_and_its_worktree_share_main_root(self):
        repo = self.root / 'separate'
        repo.mkdir()
        self.git(repo, 'init', '--separate-git-dir', str(self.root / 'git-metadata'))
        self.git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '-m', 'initial')
        subdir = repo / 'src'
        subdir.mkdir()
        expected = storage.hindsight_project(repo)
        self.assertEqual(expected[0], repo)
        self.assertEqual(storage.hindsight_project(subdir), expected)
        worktree = self.root / 'separate-worktree'
        self.git(repo, 'worktree', 'add', '-b', 'separate-test', str(worktree))
        # Without core.worktree Git does not record the original main checkout
        # for this unusual layout. Refuse to guess from the linked checkout.
        with self.assertRaisesRegex(ValueError, 'core.worktree'):
            storage.hindsight_project(worktree)
        self.git(repo, 'config', 'core.worktree', str(repo))
        self.assertEqual(storage.hindsight_project(worktree), expected)

    def test_submodule_subdirectory_uses_submodule_root(self):
        origin = self.root / 'origin'
        origin.mkdir()
        self.git(origin, 'init')
        self.git(origin, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '-m', 'initial')
        parent = self.root / 'parent'
        parent.mkdir()
        self.git(parent, 'init')
        self.git(parent, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(origin), 'child')
        child = parent / 'child'
        nested = child / 'src'
        nested.mkdir()
        self.assertEqual(storage.hindsight_project(child)[0], child)
        self.assertEqual(storage.hindsight_project(nested), storage.hindsight_project(child))
        self.assertNotEqual(storage.hindsight_project(child), storage.hindsight_project(parent))

    def test_same_basename_different_roots_and_parallel_configs(self):
        self.put('config/hindsight.json', self.config)
        projects = [self.root / name / 'repo' for name in ('one', 'two')]
        for project in projects:
            project.mkdir(parents=True)
        first = self.prepare(projects[0])
        first_path = Path(first['HINDSIGHT_CONFIG'])
        first_bytes = first_path.read_bytes()
        second = self.prepare(projects[1])
        self.assertNotEqual(first['HINDSIGHT_CONFIG'], second['HINDSIGHT_CONFIG'])
        self.assertEqual(first_path.read_bytes(), first_bytes)
        self.assertNotEqual(json.loads(first_bytes)['bankId'],
                            json.loads(Path(second['HINDSIGHT_CONFIG']).read_text())['bankId'])
        self.assertEqual(first, self.prepare(projects[0]))

    def test_git_failure_does_not_guess_bank(self):
        with patch.object(storage.subprocess, 'run', return_value=storage.subprocess.CompletedProcess(
                ['git'], 128, '', 'fatal: detected dubious ownership')):
            with self.assertRaisesRegex(ValueError, 'git probe failed'):
                storage.hindsight_project(self.root)

    def test_explicit_pilot_mapping_remains_compatible(self):
        config = {k: v for k, v in self.config.items() if k != 'bankMode'}
        config['mapPathToBank'] = {'/home/q/2_Code/infra': 'dev-infra'}
        self.put('config/hindsight.json', config)
        resolved = json.loads(Path(self.prepare()['HINDSIGHT_CONFIG']).read_text())
        self.assertEqual(resolved['mapPathToBank'], config['mapPathToBank'])
        self.assertNotIn('bankId', resolved)

    def test_project_mode_rejects_all_bank_overrides_and_unknown_mode(self):
        for extra in ({'bankId': 'shared'}, {'dynamicBankId': True},
                      {'bankIdTemplate': 'shared'}, {'bankMode': 'typo'}):
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
