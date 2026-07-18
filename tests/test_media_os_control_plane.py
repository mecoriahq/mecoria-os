import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "mecoria_media_os.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "mecoria_media_os",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MediaOSControlPlaneTests(unittest.TestCase):
    def test_status_all_is_available(self):
        module = load_module()
        result = module.build_all_status()

        self.assertEqual(result["channel_count"], 2)
        self.assertTrue(result["media_runner_ready"])
        self.assertTrue(result["notion_sync_runner_ready"])

    def test_run_plan_does_not_execute_by_default(self):
        module = load_module()
        result = module.command_run(
            channel="all",
            execute=False,
        )

        self.assertEqual(result, 0)

    def test_second_channel_bootstrap_is_visible(self):
        module = load_module()
        result = module.command_bootstrap("channel_002")

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
