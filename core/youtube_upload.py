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

    if (
        visibility == "public"
        and context.get(
            "release",
            {}
        ).get("public_release_approved")
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

    context.setdefault("release", {}).update({
        "youtube_visibility": visibility,
        "uploaded_at": utc_now(),
        "uploaded_by": "founder",
        "founder_video_review_approved": False,
        "public_release_approved": False
    })

    context.setdefault("history", []).append({
        "agent": "youtube_upload",
        "status": f"uploaded_{visibility}",
        "output_reference": canonical_url,
        "recorded_at": utc_now()
    })

    context["status"] = (
        "uploaded_for_founder_review"
    )
    context["next_agent"] = (
        "founder_video_review"
    )

    return context
