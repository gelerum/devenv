"""Run with: python3 -m unittest discover -s tests -v."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PiConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agent = self.home / ".pi/agent"
        self.config = self.home / ".config/devenv/pi"
        self.dotfiles = self.root / "dot files"

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def initialize(self, success=True, extra_env=None):
        result = subprocess.run(
            ["sh", str(ROOT / "scripts/init-pi-config.sh"), str(self.dotfiles)],
            env={**os.environ, "HOME": str(self.home), **(extra_env or {})},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_empty_host(self):
        self.initialize()
        for path in [self.agent / "auth.json", self.config / "settings.json", self.config / "models.json"]:
            self.assertEqual(json.loads(path.read_text()), {})
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.agent / "sessions").is_dir())
        self.assertTrue((self.agent / "memory").is_dir())
        self.assertFalse((self.config / "auth.json").exists())

    def test_migrate_host_settings_and_dotfiles_models(self):
        settings = self.dotfiles / "pi/.pi/agent/settings.json"
        models = self.dotfiles / "pi/.pi/agent/models.json"
        self.put(settings, {"defaultModel": "host-choice"})
        self.put(models, {"contextWindow": 500000})
        self.agent.mkdir(parents=True)
        (self.agent / "settings.json").symlink_to(settings)
        self.initialize()
        self.assertEqual(json.loads((self.config / "settings.json").read_text()), {"defaultModel": "host-choice"})
        self.assertEqual(json.loads((self.config / "models.json").read_text()), {"contextWindow": 500000})
        self.assertFalse((self.config / "settings.json").is_symlink())
        self.put(settings, {"defaultModel": "changed-dotfiles"})
        self.initialize()
        self.assertEqual(json.loads((self.config / "settings.json").read_text()), {"defaultModel": "host-choice"})

    def test_host_settings_take_priority_over_dotfiles(self):
        self.put(self.agent / "settings.json", {"defaultModel": "host"})
        self.put(self.dotfiles / "pi/.pi/agent/settings.json", {"defaultModel": "dotfiles"})
        self.initialize()
        self.assertEqual(json.loads((self.config / "settings.json").read_text())["defaultModel"], "host")

    def test_synced_config_is_not_overwritten(self):
        self.put(self.config / "settings.json", {"defaultModel": "synced"})
        self.put(self.agent / "settings.json", {"defaultModel": "old-host"})
        self.initialize()
        self.assertEqual(json.loads((self.config / "settings.json").read_text())["defaultModel"], "synced")

    def test_syncthing_publish_during_initialization_is_preserved(self):
        # Simulate Syncthing publishing after the existence check, just before ln.
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "ln"
        wrapper.write_text(
            '#!/bin/sh\n'
            'if [ "$3" = "$PI_RACE_TARGET" ]; then\n'
            '    printf \'{"defaultModel":"synced-during-init"}\\n\' > "$3"\n'
            'fi\n'
            'exec /usr/bin/ln "$@"\n'
        )
        wrapper.chmod(0o755)
        self.put(self.agent / "settings.json", {"defaultModel": "old-host"})
        self.initialize(extra_env={
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "PI_RACE_TARGET": str(self.config / "settings.json"),
        })
        self.assertEqual(
            json.loads((self.config / "settings.json").read_text())["defaultModel"],
            "synced-during-init",
        )
        self.assertFalse(list(self.config.glob(".syncthing.*.tmp")))

    def test_reject_directory_or_symlink_in_sync_folder(self):
        self.config.mkdir(parents=True)
        target = self.config / "settings.json"
        target.mkdir()
        self.initialize(success=False)
        target.rmdir()
        source = self.root / "outside.json"
        self.put(source, {})
        target.symlink_to(source)
        self.initialize(success=False)
        source.unlink()
        self.initialize(success=False)

    def run_entrypoint_config(self, success=True):
        # Execute only the config setup, without Claude setup or Nix initialization.
        setup = (ROOT / "entrypoint.sh").read_text().split("# Claude Code", 1)[0]
        setup = setup.replace("/run/pi-config", str(self.config))
        result = subprocess.run(
            ["sh", "-c", setup],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_entrypoint_links_follow_replacement_and_write_back(self):
        self.initialize()
        self.put(self.agent / "settings.json", {"old": True})
        self.run_entrypoint_config()
        settings = self.agent / "settings.json"
        self.assertTrue(settings.is_symlink())
        self.assertTrue((self.agent / "models.json").is_symlink())
        replacement = self.config / "settings.new"
        self.put(replacement, {"defaultModel": "synced"})
        replacement.replace(self.config / "settings.json")
        self.assertEqual(json.loads(settings.read_text())["defaultModel"], "synced")
        self.put(settings, {"defaultModel": "saved-by-pi"})
        self.assertEqual(json.loads((self.config / "settings.json").read_text())["defaultModel"], "saved-by-pi")
        self.run_entrypoint_config()

    def test_entrypoint_without_mount_preserves_image_defaults(self):
        self.put(self.agent / "settings.json", {"defaultModel": "image-default"})
        self.run_entrypoint_config()
        self.assertEqual(json.loads((self.agent / "settings.json").read_text())["defaultModel"], "image-default")
        self.assertFalse((self.agent / "settings.json").is_symlink())

    def test_entrypoint_rejects_incomplete_config(self):
        self.config.mkdir(parents=True)
        self.run_entrypoint_config(success=False)


if __name__ == "__main__":
    unittest.main()
