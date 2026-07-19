import ast
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = (
    ROOT / "agents" / "media_video_orchestrator" / "run.py"
)


def load_recovery_namespace(project_root: Path):
    tree = ast.parse(
        ORCHESTRATOR.read_text(encoding="utf-8-sig")
    )
    names = {
        "canonical_script_path",
        "relative_project_path",
        "recover_locked_factual_candidate",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in names
    ]
    namespace = {
        "Path": Path,
        "PROJECT_ROOT": project_root,
        "factual_pipeline_required": lambda profile: True,
        "append_history": lambda **kwargs: kwargs["context"].setdefault(
            "history", []
        ).append(
            {
                "agent": kwargs["agent"],
                "status": kwargs["status"],
                "reference": kwargs.get("reference"),
            }
        ),
        "set_status": lambda context, status, next_agent: {
            **context,
            "status": status,
            "next_agent": next_agent,
        },
        "save_context": lambda context: None,
    }

    def restore_best_candidate_script(
        *,
        project_root,
        context,
        canonical_script_path,
    ):
        reference = context["quality_gates"][
            "fact_risk_best_candidate"
        ]["script_reference"]
        data = json.loads(
            (project_root / reference).read_text()
        )
        canonical_script_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        canonical_script_path.write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        return data

    namespace["restore_best_candidate_script"] = (
        restore_best_candidate_script
    )
    module = ast.Module(body=selected, type_ignores=[])
    exec(
        compile(module, str(ORCHESTRATOR), "exec"),
        namespace,
    )
    return namespace


class FactualCandidateRecoveryTests(unittest.TestCase):
    def test_legacy_full_rewrite_state_restores_locked_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reference = (
                "records/run_contexts/rise_dossier/video_001/"
                "candidates/candidate_04/script.json"
            )
            source = root / reference
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                json.dumps(
                    {
                        "agent": "script",
                        "script": {
                            "title": "Theranos",
                        },
                    }
                ),
                encoding="utf-8",
            )
            context = {
                "channel": "rise_dossier",
                "video_id": "video_001",
                "run_id": "rise_dossier_video_001_v1",
                "status": "topic_approved",
                "next_agent": "script",
                "outputs": {
                    "claims_ledger": "claims.json",
                },
                "sources": {
                    "editorial_revision_brief": "revision.json",
                },
                "quality_gates": {
                    "editorial_standard_revision_count": 3,
                    "fact_risk_section_repair_count": 3,
                    "editorial_candidate_count": 2,
                    "editorial_best_candidate": {"candidate_index": 2},
                    "fact_risk_best_candidate": {
                        "script_reference": reference,
                        "metrics": {"approved": True},
                    },
                },
            }
            namespace = load_recovery_namespace(root)
            recovered = namespace[
                "recover_locked_factual_candidate"
            ](
                context=context,
                profile={"factuality": {"pipeline_required": True}},
            )

            canonical = (
                root
                / "agents"
                / "script"
                / "output"
                / "rise_dossier"
                / "video_001"
                / "rise_dossier_video_001_v1"
                / "script.json"
            )
            self.assertTrue(canonical.exists())
            self.assertEqual(recovered["status"], "script_ready")
            self.assertEqual(recovered["next_agent"], "seo")
            self.assertNotIn(
                "editorial_revision_brief",
                recovered["sources"],
            )
            self.assertEqual(
                recovered["quality_gates"][
                    "editorial_repair_policy_version"
                ],
                "section_level_v1",
            )
            self.assertEqual(
                recovered["quality_gates"][
                    "editorial_standard_revision_count"
                ],
                0,
            )
            self.assertEqual(
                recovered["quality_gates"][
                    "fact_risk_section_repair_count"
                ],
                0,
            )
            self.assertEqual(
                recovered["quality_gates"][
                    "editorial_candidate_count"
                ],
                0,
            )
            self.assertNotIn(
                "editorial_best_candidate",
                recovered["quality_gates"],
            )


if __name__ == "__main__":
    unittest.main()
