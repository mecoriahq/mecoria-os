import tempfile
import unittest
from pathlib import Path

from core.content_usage_registry import (
    assert_content_batch_registered,
    build_content_record,
    register_content_batch,
    validate_content_batch,
)


class ContentUsageRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = (
            Path(self.temp_dir.name)
            / "content_usage_registry.json"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def build_record(
        self,
        record_type: str,
        text: str,
        video_id: str,
        source_name: str
    ) -> dict:
        return build_content_record(
            record_type=record_type,
            payload=text,
            channel="hiddenova",
            video_id=video_id,
            run_id=f"hiddenova_{video_id}_v1",
            source_reference=source_name
        )

    def test_same_video_is_idempotent(self):
        record = self.build_record(
            "script",
            (
                "A hidden airport system moves luggage "
                "through scanners belts and routing software."
            ),
            "video_001",
            "script.json"
        )

        register_content_batch(
            [record],
            registry_path=self.registry_path
        )
        register_content_batch(
            [record],
            registry_path=self.registry_path
        )

        assert_content_batch_registered(
            [record],
            registry_path=self.registry_path
        )

    def test_exact_duplicate_other_video_is_blocked(self):
        first = self.build_record(
            "script",
            (
                "This documentary reveals the hidden "
                "airport baggage routing network."
            ),
            "video_001",
            "script.json"
        )

        duplicate = self.build_record(
            "script",
            (
                "This documentary reveals the hidden "
                "airport baggage routing network."
            ),
            "video_002",
            "renamed_script.json"
        )

        register_content_batch(
            [first],
            registry_path=self.registry_path
        )

        with self.assertRaises(ValueError):
            validate_content_batch(
                [duplicate],
                registry_path=self.registry_path
            )

    def test_small_script_edits_are_blocked(self):
        first = self.build_record(
            "script",
            (
                "Every checked bag enters a hidden airport "
                "network of conveyor belts scanners routing "
                "software workers and loading systems before "
                "it reaches the aircraft."
            ),
            "video_001",
            "script.json"
        )

        edited = self.build_record(
            "script",
            (
                "Every checked suitcase enters a hidden airport "
                "network of conveyor belts scanners routing "
                "software staff and loading systems before "
                "it finally reaches the aircraft."
            ),
            "video_002",
            "script.json"
        )

        register_content_batch(
            [first],
            registry_path=self.registry_path
        )

        with self.assertRaises(ValueError):
            validate_content_batch(
                [edited],
                registry_path=self.registry_path
            )

    def test_near_duplicate_thumbnail_is_blocked(self):
        first = self.build_record(
            "thumbnail_strategy",
            "WHERE BAGS GO",
            "video_001",
            "thumbnail.json"
        )

        edited = self.build_record(
            "thumbnail_strategy",
            "WHERE YOUR BAGS GO",
            "video_002",
            "thumbnail.json"
        )

        register_content_batch(
            [first],
            registry_path=self.registry_path
        )

        with self.assertRaises(ValueError):
            validate_content_batch(
                [edited],
                registry_path=self.registry_path
            )

    def test_different_content_is_allowed(self):
        first = self.build_record(
            "script",
            (
                "Inside the global cold chain that keeps "
                "medicine and food safe."
            ),
            "video_001",
            "script.json"
        )

        different = self.build_record(
            "script",
            (
                "How undersea internet cables connect "
                "continents and carry global data."
            ),
            "video_002",
            "script.json"
        )

        register_content_batch(
            [first],
            registry_path=self.registry_path
        )

        validate_content_batch(
            [different],
            registry_path=self.registry_path
        )

    def test_record_types_are_isolated(self):
        script = self.build_record(
            "script",
            "WHERE BAGS GO",
            "video_001",
            "script.json"
        )

        thumbnail = self.build_record(
            "thumbnail_strategy",
            "WHERE BAGS GO",
            "video_002",
            "thumbnail.json"
        )

        register_content_batch(
            [script],
            registry_path=self.registry_path
        )

        validate_content_batch(
            [thumbnail],
            registry_path=self.registry_path
        )


if __name__ == "__main__":
    unittest.main()
