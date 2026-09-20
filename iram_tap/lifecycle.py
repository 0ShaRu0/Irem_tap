from __future__ import annotations

import logging
from contextlib import ExitStack
from typing import Callable

logger = logging.getLogger(__name__)


class Resources:
    """LIFO cleanup that continues when an individual device fails to stop."""

    def __init__(self) -> None:
        self._stack = ExitStack()

    def add(self, close: Callable[[], object]) -> None:
        def cleanup() -> None:
            try:
                close()
            except Exception:
                logger.exception("자원 종료 실패: %s", close)
        self._stack.callback(cleanup)

    def close(self) -> None:
        self._stack.close()
