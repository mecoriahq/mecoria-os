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
    audit_group_imports,
    evaluate_download_relevance,
    import_group_downloads,
    import_existing_downloads,
    missing_groups,
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

    def test_groups_keep_generic_catalog_role_ids(self):
        script = sample_script()
        catalog = build_role_catalog(script)
        groups = build_search_groups(
            script_data=script,
            role_catalog=catalog,
        )

        self.assertEqual(
            groups[0]["catalog_role_id"],
            "route_planning",
        )
        self.assertEqual(
            groups[1]["catalog_role_id"],
            "truck_compaction",
        )
        self.assertFalse(
            groups[0]["catalog_role_id"].startswith("payment_")
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

    def test_explicit_bridge_role_hint_needs_filename_evidence(self):
        catalog = build_role_catalog(
            sample_script()
        )
        target_role = next(
            item["role_id"]
            for item in catalog
            if item["role_id"] == "truck_compaction"
        )
        filename = (
            f"mecoria-role-{target_role}__001__"
            "garbage-truck-hydraulic-bin-compactor-"
            "SBV-123456789.mp4"
        )

        result = classify_file(
            filename=filename,
            role_catalog=catalog,
        )

        self.assertEqual(
            result["role"],
            target_role,
        )
        self.assertIn(
            result["classification_confidence"],
            {"medium", "high"},
        )
        self.assertGreater(
            result["classification_score"],
            0,
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
                "role_id": "sb_01_truck_compaction",
                "catalog_role_id": "truck_compaction",
                "role_title": "Truck Compaction",
                "query": "garbage truck hydraulic bin compactor",
                "visual_direction": (
                    "Garbage truck lifting bins and compacting waste."
                ),
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

    def test_relevance_rejects_unrelated_crane_clip(self):
        group = {
            "role_title": "Inside the Truck, Space Becomes Time",
            "query": "hydraulic arms lifting bins compacting plates truck",
            "visual_direction": (
                "Garbage truck compactor lifting bins and compressing waste."
            ),
        }
        result = evaluate_download_relevance(
            "precast-concrete-slabs-lowered-by-crane.mp4",
            group,
        )
        self.assertFalse(result["approved"])

    def test_relevance_accepts_topic_specific_clip(self):
        group = {
            "role_title": "Inside the Truck, Space Becomes Time",
            "query": "hydraulic arms lifting bins compacting plates truck",
            "visual_direction": (
                "Garbage truck compactor lifting bins and compressing waste."
            ),
        }
        result = evaluate_download_relevance(
            "garbage-truck-hydraulic-bin-compactor.mp4",
            group,
        )
        self.assertTrue(result["approved"])

    def test_audit_quarantines_irrelevant_existing_clip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = {
                "channel": "hiddenova",
                "video_id": "video_005",
                "run_id": "hiddenova_video_005_v1",
            }
            group = {
                "group_index": 2,
                "role_id": "sb_02_inside_the_truck",
                "catalog_role_id": "truck_compaction",
                "role_title": "Truck Compaction",
                "query": "garbage truck hydraulic bin compactor",
                "visual_direction": (
                    "Garbage truck lifting bins and compacting waste."
                ),
            }

            with patch(
                "agents.storyblocks_bridge.run.PROJECT_ROOT",
                root,
            ):
                active = (
                    root / "assets" / "stock" / "hiddenova"
                    / "video_005" / "storyblocks"
                    / "02_sb_02_inside_the_truck"
                )
                active.mkdir(parents=True)
                bad = active / (
                    "mecoria-role-sb_02_inside_the_truck__001__"
                    "precast-concrete-crane.mp4"
                )
                bad.write_bytes(b"bad")
                result = audit_group_imports(context, group)

            self.assertEqual(len(result["rejected"]), 1)
            self.assertFalse(bad.exists())

    def test_slug_normalization_is_stable(self):
        self.assertEqual(
            normalize_slug(
                "Waste & Transfer  Station!"
            ),
            "waste-and-transfer-station",
        )


class ExistingDownloadsImportTests(unittest.TestCase):
    def test_existing_downloads_import_unique_relevant_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = {
                "channel": "hiddenova",
                "video_id": "video_005",
                "run_id": "hiddenova_video_005_v1",
            }
            groups = build_search_groups(
                script_data=sample_script(),
                role_catalog=build_role_catalog(
                    script_data=sample_script(),
                    visual_plan_data=None,
                ),
                target_clip_count=6,
                minimum_roles=6,
            )
            downloads = root / "Downloads"
            downloads.mkdir()
            clip = downloads / "garbage-truck-city-street-waste-collection.mp4"
            clip.write_bytes(b"unique-video")

            with patch(
                "agents.storyblocks_bridge.run.PROJECT_ROOT",
                root,
            ):
                report = import_existing_downloads(
                    context=context,
                    groups=groups,
                    downloads_dir=downloads,
                    max_age_hours=24,
                )
                self.assertEqual(len(report["imported"]), 1)
                self.assertEqual(len(report["duplicate"]), 0)
                self.assertEqual(len(missing_groups(context, groups)), 5)


if __name__ == "__main__":
    unittest.main()
