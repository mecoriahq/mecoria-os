import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import validate
from openai import OpenAI

from prompt import build_prompt
from output import save_output


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.channel_content_policy import (
    factual_pipeline_required,
    load_editorial_profile,
)
from core.video_run_context import (
    load_context,
    register_output,
    resolve_output,
    save_context,
    set_status,
)
from core.content_quality import (
    DEFAULT_EDITORIAL_OVERALL_MIN,
    EDITORIAL_CRITICAL_CHECKS,
    evaluate_editorial_structure,
    evaluate_hiddenova_channel_contract,
    evaluate_qa_editorial_gate,
    evaluate_script_word_count,
)

DEFAULT_CHANNEL = "hiddenova"

ALL_CHECKS = (
    "script_quality",
    "hook_strength",
    "hook_intro_distinctness",
    "narrative_spine",
    "specificity",
    "repetition_risk",
    "seo_alignment",
    "title_quality",
    "title_thumbnail_synergy",
    "hiddenova_brand_intro",
    "standard_cta",
    "description_quality",
    "tags_quality",
    "thumbnail_text_quality",
)


def load_json(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path}"
        )

    return json.loads(
        file_path.read_text(encoding="utf-8")
    )


def load_schema() -> dict:
    return load_json(BASE_DIR / "schema.json")


def get_script_latest_path(
    channel: str
) -> Path:
    return (
        PROJECT_ROOT
        / "agents"
        / "script"
        / "output"
        / channel.lower()
        / "latest.json"
    )


def get_seo_latest_path(
    channel: str
) -> Path:
    return (
        PROJECT_ROOT
        / "agents"
        / "seo"
        / "output"
        / channel.lower()
        / "latest.json"
    )


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1

        if start == -1 or end == 0:
            raise ValueError(
                "OpenAI response does not contain "
                "valid JSON."
            )

        return json.loads(text[start:end])


def generate_qa(prompt: str) -> dict:
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_completion_tokens=6000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError(
            "OpenAI returned an empty response."
        )

    return extract_json(content)


def build_default_checks(
    primary_status: str = "warning",
    primary_score: int = 0
) -> dict:
    return {
        name: {
            "status": primary_status,
            "score": primary_score
        }
        for name in ALL_CHECKS
    }


def build_word_count_rejection(
    word_gate: dict
) -> dict:
    checks = build_default_checks()
    checks["script_quality"] = {
        "status": "fail",
        "score": 0
    }

    return {
        "status": "rejected",
        "overall_score": 0,
        "checks": checks,
        "issues": [
            {
                "field": (
                    "script.narration_word_count"
                ),
                "severity": "high",
                "message": (
                    "Script narration word count is "
                    "outside the approved range. "
                    f"Actual: {word_gate['word_count']}. "
                    f"Required: {word_gate['minimum']} "
                    f"to {word_gate['maximum']}."
                )
            }
        ],
        "recommendations": [
            {
                "field": "script",
                "suggestion": (
                    "Regenerate the script within the "
                    "required narration word range before "
                    "audio or visual production."
                )
            }
        ]
    }


def score_status(
    score: int,
    minimum: int
) -> str:
    if score >= minimum:
        return "pass"

    if score >= max(0, minimum - 10):
        return "warning"

    return "fail"


def append_unique_issue(
    issues: list[dict],
    issue: dict
) -> None:
    signature = (
        issue.get("field"),
        issue.get("message"),
    )

    existing = {
        (
            item.get("field"),
            item.get("message"),
        )
        for item in issues
    }

    if signature not in existing:
        issues.append(issue)


def append_unique_recommendation(
    recommendations: list[dict],
    recommendation: dict
) -> None:
    signature = (
        recommendation.get("field"),
        recommendation.get("suggestion"),
    )

    existing = {
        (
            item.get("field"),
            item.get("suggestion"),
        )
        for item in recommendations
    }

    if signature not in existing:
        recommendations.append(
            recommendation
        )


def normalize_model_checks(
    qa_data: dict
) -> dict:
    supplied = qa_data.get("checks", {})
    normalized = build_default_checks(
        primary_status="fail",
        primary_score=0
    )

    for name in ALL_CHECKS:
        check = supplied.get(name)

        if not isinstance(check, dict):
            continue

        normalized[name] = {
            "status": str(
                check.get("status", "fail")
            ).lower(),
            "score": max(
                0,
                min(
                    100,
                    int(check.get("score", 0))
                )
            )
        }

    return normalized


def apply_deterministic_checks(
    script_data: dict,
    seo_data: dict,
    checks: dict,
    issues: list[dict],
    recommendations: list[dict],
    thresholds: dict,
    gates: dict
) -> None:
    structure = evaluate_editorial_structure(
        script_data
    )

    for name, result in (
        structure.get("checks", {})
    ).items():
        existing_score = int(
            checks.get(
                name,
                {}
            ).get("score", 0)
        )
        merged_score = min(
            existing_score,
            int(result["score"])
        )
        minimum = int(
            thresholds.get(
                name,
                EDITORIAL_CRITICAL_CHECKS.get(
                    name,
                    80
                )
            )
        )

        checks[name] = {
            "score": merged_score,
            "status": score_status(
                merged_score,
                minimum
            )
        }

    for issue in structure.get(
        "issues",
        []
    ):
        append_unique_issue(
            issues,
            issue
        )

    contract = evaluate_hiddenova_channel_contract(
        script_data=script_data,
        require_brand_intro=bool(
            gates.get(
                "require_channel_brand_intro",
                gates.get(
                    "require_hiddenova_brand_intro",
                    False,
                ),
            )
        ),
        require_standard_cta=bool(
            gates.get(
                "require_standard_cta",
                False
            )
        ),
        brand_name=str(
            gates.get(
                "channel_brand_name",
                "Hiddenova",
            )
        ),
        brand_intro_scan_words=int(
            gates.get(
                "channel_brand_intro_scan_words",
                25,
            )
        ),
    )

    for name, result in contract["checks"].items():
        minimum = int(
            thresholds.get(name, 100)
        )
        checks[name] = {
            "score": int(result["score"]),
            "status": score_status(
                int(result["score"]),
                minimum
            )
        }

    for issue in contract.get("issues", []):
        append_unique_issue(issues, issue)

    if not contract["checks"][
        "hiddenova_brand_intro"
    ]["score"]:
        append_unique_recommendation(
            recommendations,
            {
                "field": "script.introduction",
                "suggestion": (
                    "Add the configured channel brand name "
                    "within the required opening window, then "
                    "immediately advance the story."
                )
            }
        )

    if not contract["checks"][
        "standard_cta"
    ]["score"]:
        append_unique_recommendation(
            recommendations,
            {
                "field": "script.call_to_action",
                "suggestion": (
                    "Write a concise final CTA that "
                    "explicitly asks viewers to comment, "
                    "like, and subscribe."
                )
            }
        )

    seo = seo_data.get("seo", {})
    chapters = seo.get("chapters", [])

    if chapters:
        checks["seo_alignment"] = {
            "status": "fail",
            "score": min(
                60,
                checks["seo_alignment"]["score"]
            )
        }
        append_unique_issue(
            issues,
            {
                "field": "seo.chapters",
                "severity": "high",
                "message": (
                    "Estimated SEO chapter timestamps "
                    "are not allowed. Actual chapters "
                    "must be created from assembled audio."
                )
            }
        )
        append_unique_recommendation(
            recommendations,
            {
                "field": "seo.chapters",
                "suggestion": (
                    "Return an empty chapters array. "
                    "The publisher will add actual "
                    "timestamps after audio assembly."
                )
            }
        )

    thumbnail_text = str(
        seo.get("thumbnail_text", "")
    ).strip()
    thumbnail_words = [
        item
        for item in thumbnail_text.split()
        if item
    ]
    thumbnail_valid = (
        2 <= len(thumbnail_words) <= 4
        and thumbnail_text
        == thumbnail_text.upper()
    )

    if not thumbnail_valid:
        checks["thumbnail_text_quality"] = {
            "status": "fail",
            "score": min(
                60,
                checks[
                    "thumbnail_text_quality"
                ]["score"]
            )
        }
        checks["title_thumbnail_synergy"] = {
            "status": "fail",
            "score": min(
                70,
                checks[
                    "title_thumbnail_synergy"
                ]["score"]
            )
        }
        append_unique_issue(
            issues,
            {
                "field": "seo.thumbnail_text",
                "severity": "high",
                "message": (
                    "Thumbnail text must be 2 to 4 "
                    "ALL-CAPS words with a direct, "
                    "visually clear tension."
                )
            }
        )


def build_thresholds(
    gates: dict
) -> dict:
    thresholds = {
        "hook_strength": int(
            gates.get(
                "minimum_hook_strength_score",
                EDITORIAL_CRITICAL_CHECKS[
                    "hook_strength"
                ]
            )
        ),
        "hook_intro_distinctness": int(
            gates.get(
                (
                    "minimum_hook_intro_"
                    "distinctness_score"
                ),
                EDITORIAL_CRITICAL_CHECKS[
                    "hook_intro_distinctness"
                ]
            )
        ),
        "narrative_spine": int(
            gates.get(
                "minimum_narrative_spine_score",
                EDITORIAL_CRITICAL_CHECKS[
                    "narrative_spine"
                ]
            )
        ),
        "specificity": int(
            gates.get(
                "minimum_specificity_score",
                EDITORIAL_CRITICAL_CHECKS[
                    "specificity"
                ]
            )
        ),
        "repetition_risk": int(
            gates.get(
                "minimum_repetition_risk_score",
                EDITORIAL_CRITICAL_CHECKS[
                    "repetition_risk"
                ]
            )
        ),
        "title_thumbnail_synergy": int(
            gates.get(
                (
                    "minimum_title_thumbnail_"
                    "synergy_score"
                ),
                EDITORIAL_CRITICAL_CHECKS[
                    "title_thumbnail_synergy"
                ]
            )
        ),
    }

    if gates.get(
        "require_channel_brand_intro",
        gates.get("require_hiddenova_brand_intro", False)
    ):
        thresholds["hiddenova_brand_intro"] = 100

    if gates.get(
        "require_standard_cta",
        False
    ):
        thresholds["standard_cta"] = 100

    return thresholds


def normalize_output(
    script_data: dict,
    seo_data: dict,
    qa_data: dict,
    gates: dict
) -> dict:
    checks = normalize_model_checks(qa_data)

    raw_issues = qa_data.get("issues", [])
    issues = (
        list(raw_issues)
        if isinstance(raw_issues, list)
        else []
    )

    raw_recommendations = qa_data.get(
        "recommendations",
        []
    )
    recommendations = (
        list(raw_recommendations)
        if isinstance(
            raw_recommendations,
            list
        )
        else []
    )
    thresholds = build_thresholds(gates)

    apply_deterministic_checks(
        script_data=script_data,
        seo_data=seo_data,
        checks=checks,
        issues=issues,
        recommendations=recommendations,
        thresholds=thresholds,
        gates=gates
    )

    for name, minimum in thresholds.items():
        checks[name]["status"] = score_status(
            checks[name]["score"],
            minimum
        )

    critical_average = round(
        sum(
            checks[name]["score"]
            for name in thresholds
        ) / len(thresholds)
    )
    model_overall = max(
        0,
        min(
            100,
            int(
                qa_data.get(
                    "overall_score",
                    0
                )
            )
        )
    )
    overall_score = min(
        model_overall,
        critical_average
    )

    provisional = {
        "status": (
            "approved"
            if qa_data.get("status") == "approved"
            else "rejected"
        ),
        "overall_score": overall_score,
        "checks": checks,
    }
    minimum_overall = int(
        gates.get(
            "minimum_editorial_overall_score",
            DEFAULT_EDITORIAL_OVERALL_MIN
        )
    )
    gate = evaluate_qa_editorial_gate(
        qa_data=provisional,
        minimum_overall=minimum_overall,
        critical_thresholds=thresholds
    )

    for failure in gate["failures"]:
        check_name = failure["check"]

        if check_name in {
            "qa_status",
            "overall_score"
        }:
            continue

        append_unique_issue(
            issues,
            {
                "field": (
                    "editorial."
                    f"{check_name}"
                ),
                "severity": "high",
                "message": (
                    f"{check_name} did not meet the "
                    "production threshold. "
                    f"Actual: {failure.get('actual')}. "
                    f"Required: "
                    f"{failure.get('minimum')}."
                )
            }
        )
        append_unique_recommendation(
            recommendations,
            {
                "field": check_name,
                "suggestion": (
                    "Regenerate the script or metadata "
                    "to resolve this editorial weakness "
                    "before audio production."
                )
            }
        )

    status = (
        "approved"
        if gate["approved"]
        else "rejected"
    )
    next_agent = (
        "media_video_orchestrator"
        if status == "approved"
        else None
    )

    return {
        "agent": "qa",
        "version": "3.0",
        "channel": script_data["channel"],
        "status": status,
        "overall_score": overall_score,
        "checks": checks,
        "issues": issues,
        "recommendations": recommendations,
        "metadata": {
            "source_agents": (
                ["script", "seo", "fact_qa", "risk_review"]
                if gates.get("factual_pipeline_required", False)
                else ["script", "seo"]
            ),
            "next_agent": next_agent
        }
    }


def get_relative_path(path: Path) -> str:
    return str(
        path.relative_to(PROJECT_ROOT)
    ).replace("\\", "/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run strict editorial QA for a locked "
            "video run context."
        )
    )

    parser.add_argument(
        "--channel",
        default=DEFAULT_CHANNEL
    )
    parser.add_argument(
        "--video-id",
        default=None
    )
    parser.add_argument(
        "--dry-run",
        action="store_true"
    )

    return parser.parse_args()


def resolve_qa_inputs(
    channel: str,
    video_id: str | None
) -> tuple[dict | None, Path, dict, Path, dict]:
    if not video_id:
        script_path = get_script_latest_path(channel)
        seo_path = get_seo_latest_path(channel)

        return (
            None,
            script_path,
            load_json(script_path),
            seo_path,
            load_json(seo_path)
        )

    context = load_context(
        channel=channel,
        video_id=video_id
    )

    script_path = resolve_output(
        context=context,
        key="script"
    )
    seo_path = resolve_output(
        context=context,
        key="seo"
    )

    script_data = load_json(script_path)
    seo_data = load_json(seo_path)

    for name, data in (
        ("script", script_data),
        ("seo", seo_data)
    ):
        if (
            data.get("video_id")
            != context["video_id"]
        ):
            raise ValueError(
                f"{name} output video_id mismatch."
            )

        if (
            data.get("run_id")
            != context["run_id"]
        ):
            raise ValueError(
                f"{name} output run_id mismatch."
            )

    return (
        context,
        script_path,
        script_data,
        seo_path,
        seo_data
    )


def save_video_specific_output(
    context: dict,
    data: dict
) -> Path:
    output_dir = (
        BASE_DIR
        / "output"
        / context["channel"]
        / context["video_id"]
        / context["run_id"]
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = output_dir / "qa.json"
    output_path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=True
        ),
        encoding="utf-8"
    )

    context = register_output(
        context=context,
        agent="qa",
        reference=get_relative_path(
            output_path
        ),
        status=data["status"]
    )

    if data["status"] == "approved":
        context = set_status(
            context=context,
            status="content_qa_ready",
            next_agent=(
                "media_video_orchestrator"
            )
        )
    else:
        context = set_status(
            context=context,
            status=(
                "content_revision_required"
            ),
            next_agent=(
                "media_video_orchestrator"
            )
        )

    save_context(context)
    return output_path


def load_factual_qa_inputs(
    context: dict | None,
    editorial_profile: dict,
) -> tuple[dict | None, dict | None]:
    if not context or not factual_pipeline_required(
        editorial_profile
    ):
        return None, None

    fact_path = resolve_output(
        context=context,
        key="fact_qa",
    )
    risk_path = resolve_output(
        context=context,
        key="risk_review",
    )
    fact_qa = load_json(fact_path)
    risk_review = load_json(risk_path)

    if fact_qa.get("status") != "approved":
        raise ValueError(
            "Fact QA must be approved before editorial QA."
        )

    if risk_review.get("status") != "approved":
        raise ValueError(
            "Risk review must be approved before editorial QA."
        )

    return fact_qa, risk_review


def main() -> None:
    args = parse_args()
    channel = args.channel.lower()
    video_id = (
        args.video_id.lower()
        if args.video_id
        else None
    )

    load_dotenv(PROJECT_ROOT / ".env")

    (
        context,
        script_path,
        script_data,
        seo_path,
        seo_data
    ) = resolve_qa_inputs(
        channel=channel,
        video_id=video_id
    )

    editorial_profile = load_editorial_profile(channel)
    fact_qa_data, risk_review_data = (
        load_factual_qa_inputs(
            context=context,
            editorial_profile=editorial_profile,
        )
    )

    print(f"CHANNEL: {channel}")
    print(
        f"VIDEO_CONTEXT_ID: {video_id}"
    )
    print(
        "SCRIPT_SOURCE: "
        f"{get_relative_path(script_path)}"
    )
    print(
        "SEO_SOURCE: "
        f"{get_relative_path(seo_path)}"
    )
    print(
        "SCRIPT_TITLE: "
        f"{script_data['script']['title']}"
    )
    print(
        "SEO_TITLE: "
        f"{seo_data['seo']['video_title']}"
    )
    print(
        "EDITORIAL_STANDARD: "
        f"{editorial_profile['profile_name']}"
    )
    print(
        "FACTUAL_PIPELINE_REQUIRED: "
        f"{str(factual_pipeline_required(editorial_profile)).lower()}"
    )

    gates = (
        context.get("quality_gates", {})
        if context
        else {}
    )
    target_word_min = int(
        gates.get(
            "target_script_word_count_min",
            1250
        )
    )
    target_word_max = int(
        gates.get(
            "target_script_word_count_max",
            1650
        )
    )
    word_gate = evaluate_script_word_count(
        script_data=script_data,
        minimum=target_word_min,
        maximum=target_word_max
    )

    print(
        "SCRIPT_NARRATION_WORD_COUNT: "
        f"{word_gate['word_count']}"
    )
    print(
        "SCRIPT_WORD_GATE: "
        f"{word_gate['status']}"
    )

    if args.dry_run:
        print(
            "STATUS: qa_dry_run_ready"
        )
        return

    if not word_gate["approved"]:
        raw_qa_data = (
            build_word_count_rejection(
                word_gate
            )
        )
    else:
        prompt = build_prompt(
            script_data=script_data,
            seo_data=seo_data,
            editorial_profile=editorial_profile,
            fact_qa_data=fact_qa_data,
            risk_review_data=risk_review_data,
        )
        raw_qa_data = generate_qa(prompt)

    final_output = normalize_output(
        script_data=script_data,
        seo_data=seo_data,
        qa_data=raw_qa_data,
        gates=gates
    )

    if context:
        final_output["video_id"] = (
            context["video_id"]
        )
        final_output["run_id"] = (
            context["run_id"]
        )

    schema = load_schema()
    validate(
        instance=final_output,
        schema=schema
    )

    if context:
        output_path = save_video_specific_output(
            context=context,
            data=final_output
        )
    else:
        output_path = save_output(
            channel=script_data["channel"],
            data=final_output
        )

    print(
        "QA Agent completed successfully."
    )
    print(
        f"Status: {final_output['status']}"
    )
    print(
        f"Score: "
        f"{final_output['overall_score']}"
    )

    for name in (
        "hook_strength",
        "hook_intro_distinctness",
        "narrative_spine",
        "specificity",
        "repetition_risk",
        "title_thumbnail_synergy",
    ):
        print(
            f"{name.upper()}: "
            f"{final_output['checks'][name]['score']}"
        )

    print(
        f"Output saved to: {output_path}"
    )


if __name__ == "__main__":
    main()
