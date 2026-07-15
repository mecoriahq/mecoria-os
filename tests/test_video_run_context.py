import copy
import unittest

from core.video_run_context import (
    assert_no_latest_sources,
    load_context,
    resolve_source
)


class VideoRunContextTests(unittest.TestCase):
    def test_video_002_context_is_valid(self):
        context = load_context(
            channel="hiddenova",
            video_id="video_002"
        )

        self.assertEqual(context["video_id"], "video_002")
        self.assertEqual(
            context["run_id"],
            "hiddenova_video_002_v1"
        )

    def test_script_snapshot_exists(self):
        context = load_context(
            channel="hiddenova",
            video_id="video_002"
        )

        script_path = resolve_source(context, "script")
        self.assertTrue(script_path.exists())

    def test_latest_json_source_is_rejected(self):
        context = load_context(
            channel="hiddenova",
            video_id="video_002"
        )
        contaminated = copy.deepcopy(context)
        contaminated["sources"]["script"] = (
            "agents/script/output/hiddenova/latest.json"
        )

        with self.assertRaises(ValueError):
            assert_no_latest_sources(contaminated)


if __name__ == "__main__":
    unittest.main()
