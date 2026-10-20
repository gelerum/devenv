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

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def run_entrypoint_config(self, success=True):
        # Execute only config setup, without Claude setup or Nix initialization.
        setup = (ROOT / "entrypoint.sh").read_text().split("# Claude Code", 1)[0]
        setup = setup.replace("/run/pi-config", str(self.config))
        result = subprocess.run(
            ["sh", "-c", setup],
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_links_follow_replacement_and_write_back(self):
        self.put(self.config / "settings.json", {"defaultModel": "synced"})
        self.put(self.config / "models.json", {})
        self.put(self.agent / "settings.json", {"old": True})
        self.run_entrypoint_config()
        settings = self.agent / "settings.json"
        self.assertTrue(settings.is_symlink())
        self.assertTrue((self.agent / "models.json").is_symlink())
        replacement = self.config / "settings.new"
        self.put(replacement, {"defaultModel": "updated-by-syncthing"})
        replacement.replace(self.config / "settings.json")
        self.assertEqual(json.loads(settings.read_text())["defaultModel"], "updated-by-syncthing")
        self.put(settings, {"defaultModel": "saved-by-pi"})
        self.assertEqual(json.loads((self.config / "settings.json").read_text())["defaultModel"], "saved-by-pi")
        self.run_entrypoint_config()

    def test_replaces_image_symlink_without_changing_dotfiles(self):
        image_default = self.root / "dotfiles/settings.json"
        self.put(image_default, {"defaultModel": "image-default"})
        self.agent.mkdir(parents=True)
        (self.agent / "settings.json").symlink_to(image_default)
        self.put(self.config / "settings.json", {"defaultModel": "synced"})
        self.put(self.config / "models.json", {})
        self.run_entrypoint_config()
        self.assertEqual(json.loads(image_default.read_text())["defaultModel"], "image-default")
        self.assertEqual(json.loads((self.agent / "settings.json").read_text())["defaultModel"], "synced")

    def test_without_mount_preserves_image_defaults(self):
        self.put(self.agent / "settings.json", {"defaultModel": "image-default"})
        self.run_entrypoint_config()
        self.assertEqual(json.loads((self.agent / "settings.json").read_text())["defaultModel"], "image-default")
        self.assertFalse((self.agent / "settings.json").is_symlink())

    def test_rejects_incomplete_config_without_creating_files(self):
        self.config.mkdir(parents=True)
        self.run_entrypoint_config(success=False)
        self.assertEqual(list(self.config.iterdir()), [])

    def test_rejects_symlink_in_sync_folder(self):
        source = self.root / "outside.json"
        self.put(source, {})
        self.config.mkdir(parents=True)
        (self.config / "settings.json").symlink_to(source)
        self.put(self.config / "models.json", {})
        self.run_entrypoint_config(success=False)


if __name__ == "__main__":
    unittest.main()
