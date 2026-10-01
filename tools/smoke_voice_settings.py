"""Isolated real-Tk settings/DPAPI check; makes no API calls or recordings."""
from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from iram_tap.config.repository import load_config_strict  # noqa: E402
from iram_tap.config.secrets import unprotect_key  # noqa: E402
from iram_tap.ui.settings_editor import SettingsEditor  # noqa: E402
from iram_tap.playback_activity import PlaybackActivity  # noqa: E402
import subprocess  # noqa: E402


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        with tempfile.TemporaryDirectory(prefix="voice-settings-") as directory:
            path = Path(directory) / "config.json"
            with patch("iram_tap.ui.fish_settings.output_devices", return_value=[
                    (1, "Headset [MME]"), (2, "CABLE Input [MME]")]):
                editor = SettingsEditor(root, path)
            tab = editor.fish_tab
            tab.key.set("local-test-not-a-real-api-key")
            tab.reference.set("test-reference")
            tab.local_device.set("Headset [MME]")
            tab.virtual_device.set("CABLE Input [MME]")
            tab.mode.set("virtual")
            # Test uses the unsaved key/ID and headset even with no virtual device.
            tab.virtual_device.set("")
            with patch("iram_tap.ui.fish_settings.VoiceController") as controller:
                controller.return_value.state = "idle"
                tab.test_button.invoke()
                arguments = controller.call_args.args
                assert arguments[0]["fish_output_mode"] == "local"
                assert arguments[0]["fish_local_device"] == "Headset [MME]"
                assert arguments[0]["fish_reference_id"] == "test-reference"
                assert unprotect_key(arguments[0]["fish_api_key_protected"]) == "local-test-not-a-real-api-key"
                controller.return_value.test_voice.assert_called_once()
                assert tab.mode.get() == "virtual"
                assert not path.exists(), "A connection test must not save settings"
            tab._tester = None
            tab.virtual_device.set("CABLE Input [MME]")
            saved = editor.model.save(editor._validated_draft(), path)
            assert unprotect_key(saved["fish_api_key_protected"]) == "local-test-not-a-real-api-key"
            assert "local-test-not-a-real-api-key" not in path.read_text(encoding="utf-8")
            editor.config = saved
            editor._sync_general_variables()
            assert tab.key.get() == ""
            tab.mode.set("local")
            saved = editor.model.save(editor._validated_draft(), path)
            reloaded = load_config_strict(path)
            assert reloaded["fish_output_mode"] == "local"
            assert reloaded["fish_local_device"] == "Headset [MME]"
            assert reloaded["fish_virtual_device"] == "CABLE Input [MME]"
            assert reloaded["fish_api_key_protected"] == saved["fish_api_key_protected"]
            editor.config = saved
            tab.delete_key.set(True)
            saved = editor.model.save(editor._validated_draft(), path)
            assert saved["fish_api_key_protected"] == ""
            root.update_idletasks()
            activity = PlaybackActivity(path)
            try:
                subprocess.run([sys.executable, "-c",
                    "from pathlib import Path; from iram_tap.playback_activity import PlaybackActivity; "
                    "import sys; meter=PlaybackActivity(Path(sys.argv[1])); meter.publish(0.25)", str(path)], check=True)
                assert activity.read() == 0.25, "Settings playback must reach the overlay process"
            finally:
                activity.close()
            print("Settings UI, output switching, key encryption/preservation/deletion: OK")
            print("Unsaved key/ID headset test and cross-process lip activity: OK")
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
