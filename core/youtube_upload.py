import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse


YOUTUBE_VIDEO_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{11}$"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(str(url).strip())
    hostname = parsed.netloc.lower().removeprefix("www.")

    video_id = None

    if hostname == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]

    elif hostname in {
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com"
    }:
        if parsed.path == "/watch":
            video_id = parse_qs(
                parsed.query
            ).get("v", [None])[0]

        elif parsed.path.startswith(
            ("/shorts/", "/embed/", "/live/")
        ):
            parts = [
                part
                for part in parsed.path.split("/")
                if part
            ]

            if len(parts) >= 2:
                video_id = parts[1]

    if (
        not video_id
        or not YOUTUBE_VIDEO_ID_PATTERN.fullmatch(
            video_id
        )
    ):
        raise ValueError(
            "Invalid YouTube video URL or video ID."
        )

    return video_id


def approve_public_release(context: dict) -> dict:
    outputs = context.get("outputs", {})
    release = context.setdefault("release", {})

    if not outputs.get("youtube_video_id"):
        raise ValueError(
            "YouTube upload must be registered before "
            "public release approval."
        )

    if release.get("public_release_approved") is True:
        return context

    allowed_statuses = {
        "founder_review_required",
        "uploaded_for_founder_review"
    }

    if context.get("status") not in allowed_statuses:
        raise ValueError(
            "Video is not waiting for founder review."
        )

    now = utc_now()

    release.update({
        "founder_video_review_approved": True,
        "founder_video_review_approved_at": now,
        "public_release_approved": True,
        "public_release_approved_at": now,
        "public_release_approved_by": "founder"
    })

    context.setdefault("history", []).append({
        "agent": "founder_public_release",
        "status": "approved",
        "output_reference": outputs["youtube_url"],
        "recorded_at": now
    })

    context["status"] = "public_release_approved"
    context["next_agent"] = "youtube_visibility_public"

    return context


def register_youtube_upload(
    context: dict,
    youtube_url: str,
    visibility: str = "unlisted"
) -> dict:
    visibility = visibility.lower()

    if visibility not in {
        "unlisted",
        "private",
        "public"
    }:
        raise ValueError(
            "Unsupported YouTube visibility."
        )

    youtube_video_id = extract_youtube_video_id(
        youtube_url
    )

    canonical_url = (
        f"https://youtu.be/{youtube_video_id}"
    )

    existing_video_id = context.get(
        "outputs",
        {}
    ).get("youtube_video_id")

    if (
        existing_video_id
        and existing_video_id != youtube_video_id
    ):
        raise ValueError(
            "A different YouTube video is already "
            "registered for this context."
        )

    release = context.setdefault("release", {})

    if (
        visibility == "public"
        and release.get("public_release_approved")
        is not True
    ):
        raise ValueError(
            "Public upload requires founder public "
            "release approval."
        )

    context.setdefault("outputs", {}).update({
        "youtube_url": canonical_url,
        "youtube_video_id": youtube_video_id
    })

    now = utc_now()

    release.update({
        "youtube_visibility": visibility,
        "uploaded_at": (
            release.get("uploaded_at")
            or now
        ),
        "uploaded_by": "founder"
    })

    if visibility == "public":
        release.update({
            "founder_video_review_approved": True,
            "public_release_approved": True,
            "published_at": now
        })

        context["status"] = "public"
        context["next_agent"] = "analytics_48h"
        history_status = "visibility_public_registered"

    else:
        release.update({
            "founder_video_review_approved": False,
            "public_release_approved": False
        })

        context["status"] = (
            "uploaded_for_founder_review"
        )
        context["next_agent"] = (
            "founder_video_review"
        )
        history_status = f"uploaded_{visibility}"

    context.setdefault("history", []).append({
        "agent": "youtube_upload",
        "status": history_status,
        "output_reference": canonical_url,
        "recorded_at": now
    })

    return context
