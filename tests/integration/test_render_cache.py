import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
from PIL import Image

from iram_tap.config.validation import normalise_config
from iram_tap.rendering.images import ImageCache
from iram_tap.rendering.speech_bubble import SpeechBubbleRenderer, wrap_text
from iram_tap.rendering.renderer import LayerRenderer


class RenderCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)

    def test_failed_read_keeps_old_image_and_retries_without_metadata_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "hand.png"
            Image.new("RGBA", (4, 4), "red").save(path)
            cache = ImageCache(root / "config.json")
            spec = {"path": "hand.png", "position": [0, 0], "size": [4, 4], "keep_aspect": True}
            first = cache.load("hand", spec)
            Image.new("RGBA", (4, 4), "blue").save(path)
            with patch("pygame.image.load", side_effect=OSError("sharing violation")):
                failed = cache.load("hand", spec)
            self.assertIs(failed.surface, first.surface)
            self.assertIn("hand", cache.failed)
            recovered = cache.load("hand", spec)
            self.assertEqual(recovered.surface.get_at((0, 0)), pygame.Color("blue"))
            self.assertFalse(cache.failed)

    def test_fixed_bubble_reuses_surface(self) -> None:
        renderer = SpeechBubbleRenderer()
        first = renderer.surface("한글", False, 300)
        self.assertIs(renderer.surface("한글", False, 300), first)
        self.assertIsNot(renderer.surface("다른 글", False, 300), first)

    def test_window_setting_does_not_decode_images_or_reset_motion(self) -> None:
        config = normalise_config({})
        renderer = LayerRenderer(config, Path(__file__).resolve().parents[2] / "config.json")
        renderer._right_position = [7, 8]
        changed = copy.deepcopy(config)
        changed["window_x"] = 55
        with patch("pygame.image.load", side_effect=AssertionError("unexpected decode")):
            renderer.reload_config(changed)
        self.assertEqual(renderer._right_position, [7, 8])


class WrapTests(unittest.TestCase):
    def test_only_actual_overflow_has_ellipsis(self) -> None:
        self.assertEqual(wrap_text("one\ntwo\nend", len, 10), ["one", "two", "end"])
        self.assertEqual(wrap_text("one\ntwo\nend\nmore", len, 10), ["one", "two", "end..."])
