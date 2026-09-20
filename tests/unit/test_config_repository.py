from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iram_tap.config.migrations import rebase_external_paths
from iram_tap.config.repository import load_config_strict, update_config
from iram_tap.config.validation import normalise_config
from iram_tap.image_modes import discover_image_modes


class ConfigValidationTests(unittest.TestCase):
    def test_boolean_strings_are_not_python_truthiness(self) -> None:
        config = normalise_config({"microphone_enabled": "false", "always_on_top": "true"})
        self.assertFalse(config["microphone_enabled"])
        self.assertTrue(config["always_on_top"])

    def test_non_finite_values_are_rejected(self) -> None:
        for field in ("window_x", "window_width", "microphone_threshold"):
            for value in (float("inf"), float("nan"), "-Infinity"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    normalise_config({field: value})

    def test_oversized_images_are_rejected_before_allocation(self) -> None:
        with self.assertRaises(ValueError):
            normalise_config({"images": {"character": {"size": [100000, 100000]}}})

    def test_future_schema_is_not_silently_downgraded(self) -> None:
        with self.assertRaises(ValueError):
            normalise_config({"schema_version": 999})


class ConfigRepositoryTests(unittest.TestCase):
    def test_failed_validation_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            update_config(lambda config: {**config, "window_width": 450}, path)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                update_config(lambda config: {**config, "window_x": float("inf")}, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(load_config_strict(path)["window_width"], 450)

    def test_explicit_repair_keeps_invalid_file_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text("{invalid", encoding="utf-8")
            update_config(lambda config: config, path, repair_invalid=True)
            backups = list(path.parent.glob("config.json.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "{invalid")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 1)

    def test_rebase_preserves_custom_images_and_portable_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, bundle = root / "old", root / "bundle"
            for base in (legacy, bundle):
                (base / "image/keybord_Iram").mkdir(parents=True)
                (base / "image/keybord_Iram/character.png").write_bytes(b"default")
            (legacy / "custom.png").write_bytes(b"custom")
            config = normalise_config({"microphone_open_image": "custom.png"})
            migrated = rebase_external_paths(config, legacy, bundle)
            self.assertEqual(migrated["microphone_open_image"], str(legacy / "custom.png"))
            self.assertEqual(migrated["images"]["character"]["path"], "image/keybord_Iram/character.png")
            (legacy / "image/keybord_Iram/character.png").write_bytes(b"edited")
            migrated = rebase_external_paths(config, legacy, bundle)
            self.assertEqual(migrated["images"]["character"]["path"], str(legacy / "image/keybord_Iram/character.png"))

    def test_partial_external_folder_does_not_hide_bundled_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            user, bundle = root / "user", root / "bundle"
            (user / "image/keybord_Iram").mkdir(parents=True)
            (bundle / "image/Iram").mkdir(parents=True)
            with patch("iram_tap.image_modes.asset_roots", return_value=(user, bundle)):
                modes = discover_image_modes(user / "config.json")
            self.assertEqual([mode.name for mode in modes], ["keybord_Iram", "Iram"])
