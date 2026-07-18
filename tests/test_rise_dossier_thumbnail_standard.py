import unittest

from core.thumbnail_standard import (
    build_thumbnail_background_prompt,
    build_thumbnail_qa_checklist,
    load_thumbnail_standard,
    resolve_gold_reference_path,
    validate_thumbnail_text,
)


class RiseDossierThumbnailStandardTests(unittest.TestCase):
    def test_channel_specific_standard_loads_without_gold_asset(self):
        standard = load_thumbnail_standard(channel="rise_dossier")

        self.assertEqual(
            standard["standard_name"],
            "rise_dossier_investigative_v1",
        )
        self.assertFalse(standard["gold_reference"]["required"])
        self.assertIsNone(resolve_gold_reference_path(standard))
        self.assertEqual(
            standard["concept_system"]["candidate_count"],
            3,
        )
        self.assertEqual(
            standard["concept_system"]["finalist_count"],
            2,
        )

    def test_rise_dossier_thumbnail_text_contract(self):
        standard = load_thumbnail_standard(channel="rise_dossier")
        valid = validate_thumbnail_text(
            "THE APPLE TURNAROUND",
            standard,
        )
        invalid = validate_thumbnail_text(
            "How Apple Became The Biggest Company",
            standard,
        )

        self.assertTrue(valid["approved"])
        self.assertFalse(invalid["approved"])

    def test_prompt_blocks_misleading_crime_packaging(self):
        standard = load_thumbnail_standard(channel="rise_dossier")
        prompt = build_thumbnail_background_prompt(
            video_topic="The rise and fall of a company",
            main_subject="founder portrait beside a collapsing chart",
            thumbnail_text="THE FINAL COLLAPSE",
            standard=standard,
            concept_type="scandal_or_collapse",
        )

        self.assertIn("rise_dossier_investigative_v1", prompt)
        self.assertIn("No fabricated evidence", prompt)
        self.assertIn("fake mugshot", prompt)
        self.assertIn("unsupported criminal implication", prompt)

    def test_optional_gold_reference_passes_automatic_gate(self):
        standard = load_thumbnail_standard(channel="rise_dossier")
        result = build_thumbnail_qa_checklist(
            "THE FINAL COLLAPSE",
            standard,
        )

        self.assertTrue(
            result["automatic_checks"]["gold_reference_traceable"]
        )
        self.assertTrue(
            result["automatic_checks"]["standard_matches_channel"]
        )


if __name__ == "__main__":
    unittest.main()
