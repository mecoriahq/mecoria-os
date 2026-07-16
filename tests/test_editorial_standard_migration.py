import unittest

from agents.media_video_orchestrator.run import (
    EDITORIAL_STANDARD_VERSION,
    apply_production_quality_standard,
)


class EditorialStandardMigrationTests(unittest.TestCase):
    def test_migration_preserves_total_and_resets_current_budget(self):
        context = {
            "quality_gates": {
                "editorial_revision_count": 2,
                "editorial_standard_revision_count": 2,
                "editorial_quality_gate_passed": True,
            },
            "history": [],
        }

        result = apply_production_quality_standard(context)
        gates = result["quality_gates"]

        self.assertEqual(gates["editorial_revision_count"], 2)
        self.assertEqual(
            gates["editorial_standard_revision_count"],
            0,
        )
        self.assertEqual(
            gates["editorial_standard_version"],
            EDITORIAL_STANDARD_VERSION,
        )
        self.assertFalse(gates["editorial_quality_gate_passed"])
        self.assertEqual(
            result["history"][-1]["agent"],
            "editorial_standard_migration",
        )

    def test_same_standard_does_not_reset_budget(self):
        context = {
            "quality_gates": {
                "editorial_revision_count": 3,
                "editorial_standard_version": (
                    EDITORIAL_STANDARD_VERSION
                ),
                "editorial_standard_revision_count": 1,
            },
            "history": [],
        }

        result = apply_production_quality_standard(context)
        gates = result["quality_gates"]

        self.assertEqual(gates["editorial_revision_count"], 3)
        self.assertEqual(
            gates["editorial_standard_revision_count"],
            1,
        )
        self.assertEqual(result["history"], [])


if __name__ == "__main__":
    unittest.main()
