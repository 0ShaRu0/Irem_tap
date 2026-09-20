import copy
import tempfile
import unittest
from pathlib import Path

from iram_tap.config.repository import update_config, load_config_strict
from iram_tap.ui.settings_model import SettingsModel


class SettingsModelTests(unittest.TestCase):
    def test_unmodified_fields_keep_concurrent_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            original = update_config(lambda config: config, path)
            first, second = SettingsModel(original), SettingsModel(original)
            draft = copy.deepcopy(original)
            draft["images"]["character"]["position"] = [15, 20]
            first.save(draft, path)
            draft = copy.deepcopy(original)
            draft["images"]["right_hand_mouse"]["position"] = [25, 30]
            draft["window_x"] = 50
            saved = second.save(draft, path)
            self.assertEqual(saved["images"]["character"]["position"], [15, 20])
            self.assertEqual(saved["images"]["right_hand_mouse"]["position"], [25, 30])
            self.assertEqual(saved["window_x"], 50)

    def test_same_field_conflict_does_not_overwrite_other_editor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            original = update_config(lambda config: config, path)
            model = SettingsModel(original)
            update_config(lambda config: {**config, "window_x": 40}, path)
            with self.assertRaisesRegex(ValueError, "window_x"):
                model.save({**original, "window_x": 50}, path)
            self.assertEqual(load_config_strict(path)["window_x"], 40)
