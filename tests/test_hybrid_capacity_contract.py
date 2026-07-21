import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.hybrid_capacity import (
    CAPACITY_CONTRACT_VERSION,
    build_capacity_report_from_records,
    build_hybrid_capacity_report,
    build_stock_segment_specs,
    frames_to_seconds,
    maximum_stock_spec_duration,
    materialize_hybrid_capacity_plan,
    ai_image_specs_from_generation,
    stock_clips_from_manifest,
    seconds_to_frames,
)


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def load_module(
    name: str,
    path: Path,
    stub_output: bool = False,
):
    previous_output = sys.modules.get("output")

    if stub_output:
        output_stub = types.ModuleType("output")
        output_stub.save_output = (
            lambda *args, **kwargs: None
        )
        sys.modules["output"] = output_stub

    try:
        spec = importlib.util.spec_from_file_location(
            name,
            path,
        )

        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"Could not load module: {path}"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if stub_output:
            if previous_output is None:
                sys.modules.pop("output", None)
            else:
                sys.modules["output"] = previous_output


HYBRID = load_module(
    "hybrid_capacity_contract_hybrid",
    PROJECT_ROOT
    / "agents"
    / "hybrid_video_assembly"
    / "run.py",
    stub_output=True,
)
STOCK = load_module(
    "hybrid_capacity_contract_stock",
    PROJECT_ROOT
    / "agents"
    / "video_stock_pipeline"
    / "run.py",
)
ORCHESTRATOR = load_module(
    "hybrid_capacity_contract_orchestrator",
    PROJECT_ROOT
    / "agents"
    / "media_video_orchestrator"
    / "run.py",
)


class HybridCapacityContractTests(unittest.TestCase):
    def fixture_report(
        self,
        channel: str,
        video_id: str,
        run_id: str,
        maximum_ai_seconds: float | None = None,
    ) -> dict:
        context = load_json(
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel
            / f"{video_id}.json"
        )

        if maximum_ai_seconds is not None:
            context.setdefault(
                "quality_gates",
                {},
            )[
                "maximum_ai_image_segment_seconds"
            ] = maximum_ai_seconds

        return build_capacity_report_from_records(
            context=context,
            stock_manifest=load_json(
                PROJECT_ROOT
                / "records"
                / "run_contexts"
                / channel
                / video_id
                / "outputs"
                / "stock"
                / run_id
                / "stock_manifest.json"
            ),
            audio_assembly=load_json(
                PROJECT_ROOT
                / "agents"
                / "video_audio_pipeline"
                / "output"
                / channel
                / video_id
                / run_id
                / "audio_assembly.json"
            ),
            ai_visual_generation=load_json(
                PROJECT_ROOT
                / "agents"
                / "video_visual_pipeline"
                / "output"
                / channel
                / video_id
                / run_id
                / "ai_visual_generation.json"
            ),
        )

    def test_frame_conversion_is_deterministic(self):
        self.assertEqual(
            seconds_to_frames(6.01, rounding="floor"),
            180,
        )
        self.assertEqual(
            seconds_to_frames(6.01, rounding="ceil"),
            181,
        )
        self.assertEqual(
            frames_to_seconds(181),
            6.033333,
        )

    def test_hiddenova_video_006_fixture_passes(self):
        report = self.fixture_report(
            "hiddenova",
            "video_006",
            "hiddenova_video_006_v1",
        )
        self.assertTrue(report["approved"])
        self.assertEqual(
            report["contract_version"],
            CAPACITY_CONTRACT_VERSION,
        )
        self.assertEqual(
            report["deficit"]["frames"],
            0,
        )

    def test_rise_dossier_old_twelve_second_limit_fails(self):
        report = self.fixture_report(
            "rise_dossier",
            "video_001",
            "rise_dossier_video_001_v1",
            maximum_ai_seconds=12.0,
        )
        self.assertFalse(report["approved"])
        self.assertGreater(
            report["deficit"]["frames"],
            0,
        )

    def test_rise_dossier_current_limit_passes(self):
        report = self.fixture_report(
            "rise_dossier",
            "video_001",
            "rise_dossier_video_001_v1",
            maximum_ai_seconds=13.0,
        )
        self.assertTrue(report["approved"])

    def test_rise_dossier_report_materializes_exact_frames(self):
        channel = "rise_dossier"
        video_id = "video_001"
        run_id = "rise_dossier_video_001_v1"
        context = load_json(
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel
            / f"{video_id}.json"
        )
        stock_manifest = load_json(
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel
            / video_id
            / "outputs"
            / "stock"
            / run_id
            / "stock_manifest.json"
        )
        ai_generation = load_json(
            PROJECT_ROOT
            / "agents"
            / "video_visual_pipeline"
            / "output"
            / channel
            / video_id
            / run_id
            / "ai_visual_generation.json"
        )
        report = self.fixture_report(
            channel,
            video_id,
            run_id,
            maximum_ai_seconds=13.0,
        )
        plan = materialize_hybrid_capacity_plan(
            stock_clips=stock_clips_from_manifest(
                stock_manifest
            ),
            ai_image_specs=ai_image_specs_from_generation(
                ai_generation
            ),
            capacity_report=report,
            quality_gates=context.get("quality_gates", {}),
        )

        self.assertEqual(
            plan["allocation"]["stock_frames"],
            report["stock"]["selected_frames"],
        )
        self.assertEqual(
            plan["allocation"]["ai_image_frames"],
            report["ai_images"]["selected_frames"],
        )
        self.assertEqual(
            plan["allocation"]["stock_frames"]
            + plan["allocation"]["ai_image_frames"]
            + report["ai_video"]["frames"],
            report["target"]["frames"],
        )

    def test_hiddenova_report_materializes_exact_frames(self):
        channel = "hiddenova"
        video_id = "video_006"
        run_id = "hiddenova_video_006_v1"
        context = load_json(
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel
            / f"{video_id}.json"
        )
        stock_manifest = load_json(
            PROJECT_ROOT
            / "records"
            / "run_contexts"
            / channel
            / video_id
            / "outputs"
            / "stock"
            / run_id
            / "stock_manifest.json"
        )
        ai_generation = load_json(
            PROJECT_ROOT
            / "agents"
            / "video_visual_pipeline"
            / "output"
            / channel
            / video_id
            / run_id
            / "ai_visual_generation.json"
        )
        report = self.fixture_report(
            channel,
            video_id,
            run_id,
        )
        plan = materialize_hybrid_capacity_plan(
            stock_clips=stock_clips_from_manifest(
                stock_manifest
            ),
            ai_image_specs=ai_image_specs_from_generation(
                ai_generation
            ),
            capacity_report=report,
            quality_gates=context.get("quality_gates", {}),
        )

        self.assertEqual(
            plan["allocation"]["stock_frames"],
            report["stock"]["selected_frames"],
        )
        self.assertEqual(
            plan["allocation"]["ai_image_frames"],
            report["ai_images"]["selected_frames"],
        )

    def test_hybrid_wrapper_uses_shared_stock_math(self):
        clips = [
            {
                "asset_id": "A001",
                "candidate_id": "C001",
                "role": "test",
                "path": PROJECT_ROOT / "clip.mp4",
                "duration_seconds": 20.39,
            },
            {
                "asset_id": "A002",
                "candidate_id": "C002",
                "role": "test",
                "path": PROJECT_ROOT / "clip2.mp4",
                "duration_seconds": 10.03,
            },
        ]
        shared_specs = build_stock_segment_specs(
            clips,
            max_segments_per_clip=3,
        )
        hybrid_specs = HYBRID.build_stock_segment_specs(
            clips,
            max_segments_per_clip=3,
        )
        self.assertEqual(
            hybrid_specs,
            shared_specs,
        )
        self.assertEqual(
            HYBRID.maximum_stock_spec_duration(
                clips,
                hybrid_specs,
            ),
            maximum_stock_spec_duration(
                clips,
                shared_specs,
            ),
        )

    def test_stock_qa_consumes_capacity_report(self):
        items = [
            {
                "candidate_id": f"C{index:03d}",
                "relative_path": f"clip_{index:03d}.mp4",
                "duration_seconds": 15.0,
                "role": f"role_{index % 6}",
                "storyblocks_id": f"SBV-{index:06d}",
                "classification_confidence": "medium",
                "license_status": "public_use_confirmed",
            }
            for index in range(18)
        ]
        manifest = {
            "items": items,
            "total_duration_seconds": 270.0,
        }
        context = {
            "channel": "hiddenova",
            "video_id": "video_999",
            "run_id": "hiddenova_video_999_v1",
            "quality_gates": {
                "minimum_stock_clip_count": 30,
                "minimum_ai_insert_count": 12,
                "require_ai_visuals": True,
                "maximum_single_stock_clip_share": 0.08,
                "minimum_stock_duration_seconds": 180,
                "minimum_distinct_stock_roles": 5,
            },
        }
        report = {
            "approved": False,
            "contract_version": CAPACITY_CONTRACT_VERSION,
            "status": "insufficient",
            "target": {"seconds": 500.0},
            "stock": {"maximum_seconds": 200.0},
            "ai_images": {"maximum_seconds": 250.0},
            "ai_video": {"seconds": 0.0},
            "deficit": {"seconds": 50.0},
        }
        qa = STOCK.build_stock_qa(
            manifest,
            context,
            capacity_report=report,
        )
        self.assertEqual(qa["status"], "rejected")
        self.assertFalse(
            qa["checks"]["hybrid_capacity_contract"]
        )
        self.assertEqual(
            qa["summary"][
                "hybrid_capacity_deficit_seconds"
            ],
            50.0,
        )

    def test_orchestrator_capacity_pause_is_controlled(self):
        context = {
            "channel": "hiddenova",
            "video_id": "video_999",
            "run_id": "hiddenova_video_999_v1",
            "status": "stock_ready",
            "next_agent": "hybrid_video_assembly",
            "history": [],
        }
        report = {
            "contract_version": CAPACITY_CONTRACT_VERSION,
            "target": {"seconds": 500.0},
            "stock": {"maximum_seconds": 200.0},
            "ai_images": {"maximum_seconds": 250.0},
            "ai_video": {"seconds": 0.0},
            "deficit": {
                "frames": 1500,
                "seconds": 50.0,
                "estimated_additional_stock_clips": 4,
            },
        }

        def fake_set_status(
            context,
            status,
            next_agent,
        ):
            result = dict(context)
            result["status"] = status
            result["next_agent"] = next_agent
            return result

        with (
            patch.object(
                ORCHESTRATOR,
                "set_status",
                side_effect=fake_set_status,
            ),
            patch.object(
                ORCHESTRATOR,
                "append_history",
            ),
            patch.object(
                ORCHESTRATOR,
                "save_context",
            ),
        ):
            result = (
                ORCHESTRATOR
                .set_visual_capacity_repair_required(
                    context,
                    report,
                )
            )

        self.assertEqual(
            result["status"],
            "visual_capacity_repair_required",
        )
        self.assertIn(
            result["status"],
            ORCHESTRATOR.CONTROLLED_PAUSE_STATES,
        )
        self.assertEqual(
            result["capacity_repair"][
                "estimated_additional_stock_clips"
            ],
            4,
        )


if __name__ == "__main__":
    unittest.main()
