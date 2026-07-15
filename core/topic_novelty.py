import json
from pathlib import Path


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Required topic file not found: {path}"
        )

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def resolve_context_reference(
    context: dict,
    key: str
) -> str | None:
    if key in context.get("outputs", {}):
        return context["outputs"][key]

    return context.get("sources", {}).get(key)


def build_context_topic_brief(
    context: dict,
    project_root: Path
) -> dict:
    details = []

    topic_title = str(
        context.get("topic_title", "")
    ).strip()

    if topic_title:
        details.append(topic_title)

    script_reference = resolve_context_reference(
        context,
        "script"
    )

    if script_reference:
        script_path = project_root / script_reference

        if script_path.exists():
            script_data = load_json(script_path)
            script = script_data.get("script", {})
            source = script_data.get("source", {})

            for value in [
                script.get("title"),
                source.get("idea_title")
            ]:
                if value:
                    details.append(str(value))

    seo_reference = resolve_context_reference(
        context,
        "seo"
    )

    if seo_reference:
        seo_path = project_root / seo_reference

        if seo_path.exists():
            seo_data = load_json(seo_path)
            seo = seo_data.get("seo", {})

            for value in [
                seo.get("video_title"),
                seo.get("description")
            ]:
                if value:
                    details.append(str(value))

    return {
        "video_id": context["video_id"],
        "title": topic_title,
        "summary": " ".join(details)[:2500],
        "status": context.get("status"),
        "source": "run_context"
    }


def load_historical_topics(
    project_root: Path,
    channel: str,
    exclude_video_id: str | None = None
) -> list[dict]:
    topics_by_video = {}

    legacy_path = (
        project_root
        / "records"
        / "content"
        / "legacy_topic_history.json"
    )

    if legacy_path.exists():
        legacy_data = load_json(legacy_path)

        for topic in legacy_data.get("topics", []):
            video_id = str(
                topic.get("video_id", "")
            ).lower()

            if (
                not video_id
                or video_id == exclude_video_id
            ):
                continue

            topics_by_video[video_id] = topic

    context_dir = (
        project_root
        / "records"
        / "run_contexts"
        / channel.lower()
    )

    if context_dir.exists():
        for context_path in sorted(
            context_dir.glob("video_*.json")
        ):
            context = load_json(context_path)
            video_id = str(
                context.get("video_id", "")
            ).lower()

            if (
                not video_id
                or video_id == exclude_video_id
            ):
                continue

            topics_by_video[video_id] = (
                build_context_topic_brief(
                    context=context,
                    project_root=project_root
                )
            )

    return [
        topics_by_video[key]
        for key in sorted(topics_by_video)
    ]


def validate_novelty_analysis(
    analysis: dict,
    idea_count: int
) -> dict:
    evaluations = analysis.get("evaluations")

    if not isinstance(evaluations, list):
        raise ValueError(
            "Topic novelty response has no evaluations."
        )

    if len(evaluations) != idea_count:
        raise ValueError(
            "Topic novelty response must evaluate "
            "every research idea."
        )

    normalized = []
    seen_indexes = set()

    for item in evaluations:
        index = int(item.get("index", -1))

        if not 0 <= index < idea_count:
            raise ValueError(
                "Topic novelty evaluation index "
                "is out of range."
            )

        if index in seen_indexes:
            raise ValueError(
                "Duplicate topic evaluation index."
            )

        duplicate = item.get("duplicate")

        if not isinstance(duplicate, bool):
            raise ValueError(
                "Topic duplicate decision must be boolean."
            )

        seen_indexes.add(index)

        normalized.append({
            "index": index,
            "duplicate": duplicate,
            "closest_video_id": (
                item.get("closest_video_id")
            ),
            "novelty_score": int(
                item.get("novelty_score", 0)
            ),
            "content_score": int(
                item.get("content_score", 0)
            ),
            "reason": str(
                item.get("reason", "")
            ).strip()
        })

    if seen_indexes != set(range(idea_count)):
        raise ValueError(
            "Topic novelty response has missing indexes."
        )

    selected_index = int(
        analysis.get("selected_index", -1)
    )

    if not 0 <= selected_index < idea_count:
        raise ValueError(
            "Recommended topic index is out of range."
        )

    selected_evaluation = next(
        item
        for item in normalized
        if item["index"] == selected_index
    )

    if selected_evaluation["duplicate"]:
        raise ValueError(
            "Topic novelty agent recommended "
            "a duplicate topic."
        )

    return {
        "evaluations": normalized,
        "selected_index": selected_index,
        "score": int(analysis.get("score", 0)),
        "reason": str(
            analysis.get("reason", "")
        ).strip()
    }


def resolve_selected_index(
    analysis: dict,
    requested_index: int | None,
    idea_count: int
) -> int:
    selected_index = (
        int(analysis["selected_index"])
        if requested_index is None
        else int(requested_index)
    )

    if not 0 <= selected_index < idea_count:
        raise ValueError(
            "Selected idea index is out of range."
        )

    evaluation = next(
        item
        for item in analysis["evaluations"]
        if item["index"] == selected_index
    )

    if evaluation["duplicate"]:
        raise ValueError(
            "Selected topic overlaps with an existing "
            f"video: {evaluation.get('closest_video_id')}."
        )

    return selected_index
