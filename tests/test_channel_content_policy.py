import unittest

from core.channel_content_policy import (
    build_quality_gates,
    factual_pipeline_required,
    load_editorial_profile,
    thumbnail_standard_path,
)


class ChannelContentPolicyTests(unittest.TestCase):
    def test_hiddenova_profile_preserves_legacy_standard(self):
        profile = load_editorial_profile("hiddenova")
        gates = build_quality_gates(profile)

        self.assertEqual(
            profile["profile_name"],
            "hiddenova_editorial_v2",
        )
        self.assertFalse(factual_pipeline_required(profile))
        self.assertTrue(gates["require_hiddenova_brand_intro"])
        self.assertEqual(
            gates["thumbnail_standard_name"],
            "hiddenova_cinematic_v3",
        )

    def test_rise_dossier_profile_activates_factual_pipeline(self):
        profile = load_editorial_profile("rise_dossier")
        gates = build_quality_gates(profile)

        self.assertEqual(
            profile["profile_name"],
            "rise_dossier_editorial_v1",
        )
        self.assertTrue(factual_pipeline_required(profile))
        self.assertEqual(gates["target_script_word_count_min"], 1325)
        self.assertEqual(gates["target_script_word_count_max"], 1550)
        self.assertEqual(gates["target_video_duration_min_seconds"], 540)
        self.assertEqual(gates["target_video_duration_max_seconds"], 630)
        self.assertTrue(gates["require_claims_ledger"])
        self.assertTrue(gates["require_fact_qa"])
        self.assertTrue(gates["require_risk_review"])
        self.assertEqual(
            gates["max_factual_research_revision_attempts"],
            1,
        )
        self.assertFalse(gates["require_channel_brand_intro"])

    def test_rise_dossier_thumbnail_path_is_channel_specific(self):
        path = thumbnail_standard_path("rise_dossier")

        self.assertEqual(
            path.name,
            "rise_dossier_thumbnail_standard.json",
        )
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
