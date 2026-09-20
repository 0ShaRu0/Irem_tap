import unittest

from iram_tap.lifecycle import Resources


class LifecycleTests(unittest.TestCase):
    def test_failed_cleanup_does_not_skip_other_devices(self) -> None:
        resources = Resources()
        events = []
        resources.add(lambda: events.append("first"))
        def failure():
            events.append("failed")
            raise RuntimeError("device stop failed")
        resources.add(failure)
        resources.add(lambda: events.append("last"))
        with self.assertLogs("iram_tap.lifecycle", level="ERROR"):
            resources.close()
        resources.close()
        self.assertEqual(events, ["last", "failed", "first"])
