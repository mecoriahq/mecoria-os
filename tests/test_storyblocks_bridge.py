import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.stock_asset_ingest.run import (
    build_role_catalog,
    classify_file,
)
from agents.storyblocks_bridge.run import (
    allocate_clip_counts,
    build_search_groups,
    import_group_downloads,
    new_downloads,
    normalize_slug,
    storyblocks_search_url,
)


def sample_script() -> dict:
    return {
        "script": {
            "main_sections": [
                {
                    "title": "Route Planning",
                    "narration": "Crews move through city streets.",
                    "visual_direction": (
                        "Garbage trucks on city streets, "
                        "sanitation workers collecting bins."
                    ),
                },
                {
                    "title": "Truck Compaction",
                    "narration": "Hydraulics compress waste.",
                    "visual_direction": (
                        "Hydraulic garbage truck compactor, "
                        "bins lifted into collection vehicle."
                    ),
                },
                {
                    "title": "Transfer Station",
                    "narration": "Loads move to a tipping floor.",
                    "visual_direction": (
                        "Waste transfer station tipping floor, "
                        "loaders moving piles of trash."
                    ),
                },
                {
                    "title": "Recycling Sorting",
                    "narration": "Conveyors separate materials.",
                    "visual_direction": (
                        "Recycling sorting facility conveyor, "
                        "workers separating plastic and metal."
                    ),
                },
                {
                    "title": "Engineered Landfill",
                    "narration": "Compactors shape active cells.",
                    "visual_direction": (
                        "Landfill compactor and garbage trucks, "
                        "engineered waste disposal site."
                    ),
                },
                {
                    "title": "Overflow Failure",
                    "narration": "Delays leave waste in public.",
                    "visual_direction": (
                        "Overflowing trash bins in city streets, "
                        "garbage collection delay."
                    ),
                },
            ],
        }
    }


class StoryblocksBridgeTests(unittest.TestCase):
    def test_storyblocks_search_url_is_official_footage_search(self):
        url = storyblocks_search_url(
            "waste transfer station"
        )

        self.assertTrue(
            url.startswith(
                "https://www.storyblocks.com/video/search/"
            )
        )
        self.assertIn(
            "waste-transfer-station",
            url,
        )
        self.assertIn(
            "media-type=footage",
            url,
        )

    def test_clip_allocation_reaches_exact_target(self):
        counts = allocate_clip_counts(
            target_clip_count=30,
            role_count=6,
        )

        self.assertEqual(counts, [5, 5, 5, 5, 5, 5])
        self.assertEqual(sum(counts), 30)

    def test_search_groups_cover_six_roles_and_thirty_clips(self):
        script = sample_script()
        catalog = build_role_catalog(script)
        groups = build_search_groups(
            script_data=script,
            role_catalog=catalog,
            target_clip_count=30,
            minimum_roles=6,
        )

        self.assertEqual(len(groups), 6)
        self.assertEqual(
            sum(
                group["target_clip_count"]
                for group in groups
            ),
            30,
        )
        self.assertEqual(
            len({
                group["role_id"]
                for group in groups
            }),
            6,
        )

    def test_queries_are_derived_from_visual_direction(self):
        script = sample_script()
        catalog = build_role_catalog(script)
        groups = build_search_groups(
            script_data=script,
            role_catalog=catalog,
        )

        self.assertIn(
            "garbage",
            groups[0]["query"],
        )
        self.assertIn(
            "truck",
            groups[1]["query"],
        )

    def test_explicit_bridge_role_hint_is_high_confidence(self):
        catalog = build_role_catalog(
            sample_script()
        )
        target_role = catalog[0]["role_id"]
        filename = (
            f"mecoria-role-{target_role}__001__"
            "storyblocks-clip-SBV-123456789.mp4"
        )

        result = classify_file(
            filename=filename,
            role_catalog=catalog,
        )

        self.assertEqual(
            result["role"],
            target_role,
        )
        self.assertEqual(
            result["classification_confidence"],
            "high",
        )
        self.assertEqual(
            result["classification_score"],
            100,
        )

    def test_new_downloads_only_returns_changed_video_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_file = root / "old.mp4"
            old_file.write_bytes(b"old")
            before = {
                str(old_file.resolve()): (
                    old_file.stat().st_size,
                    old_file.stat().st_mtime_ns,
                )
            }
            new_file = root / "new.mp4"
            new_file.write_bytes(b"new")
            (root / "note.txt").write_text(
                "ignore",
                encoding="utf-8",
            )

            result = new_downloads(
                downloads_dir=root,
                before=before,
            )

            self.assertEqual(result, [new_file])

    def test_imported_files_receive_role_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "downloads"
            downloads.mkdir()
            clip = downloads / "garbage-truck-SBV-1.mp4"
            clip.write_bytes(b"unique-video")

            context = {
                "channel": "hiddenova",
                "video_id": "video_005",
                "run_id": "hiddenova_video_005_v1",
            }
            group = {
                "group_index": 1,
                "role_id": "truck_compaction",
            }

            with patch(
                "agents.storyblocks_bridge.run.PROJECT_ROOT",
                root,
            ):
                imported = import_group_downloads(
                    context=context,
                    group=group,
                    downloads=[clip],
                    required_count=1,
                )

            self.assertEqual(len(imported), 1)
            self.assertIn(
                "mecoria-role-truck_compaction__",
                imported[0].name,
            )
            self.assertTrue(imported[0].exists())

    def test_slug_normalization_is_stable(self):
        self.assertEqual(
            normalize_slug(
                "Waste & Transfer  Station!"
            ),
            "waste-and-transfer-station",
        )


if __name__ == "__main__":
    unittest.main()
