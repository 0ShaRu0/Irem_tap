from __future__ import annotations

import argparse
import logging
from pathlib import Path

from iram_tap.assets import default_config_path


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="iram_tap")
    parser.add_argument("--settings", action="store_true", help="설정 창 열기")
    parser.add_argument("--config", type=Path, default=default_config_path())
    options = parser.parse_args(arguments)
    from iram_tap.diagnostics import configure_logging
    configure_logging()
    try:
        from iram_tap.platform.windows import enable_dpi_awareness
        enable_dpi_awareness()
        if options.settings:
            from iram_tap.ui.settings_editor import run_settings
            run_settings(options.config)
            return 0
        from iram_tap.app import OverlayApp
        return OverlayApp(options.config).run()
    except Exception:
        logging.getLogger(__name__).exception("프로그램 실행 실패")
        return 1
