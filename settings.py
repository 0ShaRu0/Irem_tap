"""Compatibility entry point for the standalone settings editor."""
import sys

from iram_tap.bootstrap import main

if __name__ == "__main__":
    raise SystemExit(main(["--settings", *sys.argv[1:]]))
