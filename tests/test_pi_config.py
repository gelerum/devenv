"""Run with python3 -m unittest discover -s tests -v."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agent_storage', ROOT / 'scripts/agent_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


class AgentConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.mounts = self.root / 'mounts'

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def config(self, agent):
        base = self.mounts / agent
        for name in storage.CONFIG[agent]:
            path = base / 'config' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}' if name.endswith('.json') else '')
        (base / 'auth').mkdir(exist_ok=True)
        (base / 'data').mkdir(exist_ok=True)
        return base

    def test_links_follow_replacement_and_write_back(self):
        base = self.config('pi')
        storage.setup(self.home, self.mounts)
        settings = self.home / '.pi/agent/settings.json'
        self.assertTrue(settings.is_symlink())
        replacement = base / 'config/new.json'
        self.put(replacement, {'defaultModel': 'synced'})
        replacement.replace(base / 'config/settings.json')
        self.assertEqual(json.loads(settings.read_text())['defaultModel'], 'synced')
        self.put(settings, {'defaultModel': 'saved-by-pi'})
        self.assertEqual(json.loads((base / 'config/settings.json').read_text())['defaultModel'],
                         'saved-by-pi')
        storage.setup(self.home, self.mounts)

    def test_replaces_image_symlink_without_changing_dotfiles(self):
        self.config('claude')
        image = self.root / 'dotfiles/settings.json'
        self.put(image, {'image': True})
        native = self.home / '.claude'
        native.mkdir()
        (native / 'settings.json').symlink_to(image)
        storage.setup(self.home, self.mounts)
        self.assertEqual(json.loads(image.read_text()), {'image': True})
        self.assertEqual(json.loads((native / 'settings.json').read_text()), {})

    def test_all_clients_have_selective_links(self):
        for agent in storage.AGENTS:
            self.config(agent)
        storage.setup(self.home, self.mounts)
        for agent, files in storage.FILES.items():
            for name, target in files.items():
                native = storage.native_home(self.home, agent) / name
                if target.startswith('auth/'):
                    self.assertFalse(native.is_symlink())
                    saved = self.mounts / agent / target
                    self.assertEqual(native.read_bytes() if native.is_file() else None,
                                     saved.read_bytes() if saved.is_file() else None)
                else:
                    self.assertEqual(native.readlink(), self.mounts / agent / target)
        # Memory MUST be a directory bind mount, never a symlink from setup.
        self.assertFalse((self.home / '.codex/memories').is_symlink())
        self.assertFalse((self.mounts / 'codex/data/sqlite').exists())

    def test_without_mount_preserves_image_defaults(self):
        self.put(self.home / '.pi/agent/settings.json', {'image': True})
        storage.setup(self.home, self.mounts)
        self.assertFalse((self.home / '.pi/agent/settings.json').is_symlink())

    def test_rejects_missing_config_and_external_symlink(self):
        base = self.mounts / 'pi'
        base.mkdir(parents=True)
        with self.assertRaises(ValueError):
            storage.setup(self.home, self.mounts)
        self.config('pi')
        (base / 'config/settings.json').unlink()
        outside = self.root / 'outside.json'
        self.put(outside, {})
        (base / 'config/settings.json').symlink_to(outside)
        with self.assertRaises(ValueError):
            storage.setup(self.home, self.mounts)

    def test_init_waits_for_sync_instead_of_seeding(self):
        with self.assertRaises(ValueError):
            storage.initialize(self.home)
        self.assertFalse(storage.host_root(self.home).exists())
