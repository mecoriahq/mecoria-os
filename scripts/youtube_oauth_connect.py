import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CLIENT_SECRET_PATH = (
    PROJECT_ROOT
    / "secrets"
    / "google"
    / "client_secret.json"
)

TOKEN_PATH = (
    PROJECT_ROOT
    / "secrets"
    / "google"
    / "youtube_analytics_token.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def load_credentials() -> Credentials:
    credentials = None

    if TOKEN_PATH.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_PATH),
            SCOPES
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        if not CLIENT_SECRET_PATH.exists():
            raise FileNotFoundError(
                f"Client secret not found: {CLIENT_SECRET_PATH}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET_PATH),
            SCOPES
        )

        credentials = flow.run_local_server(
            host="localhost",
            port=0,
            authorization_prompt_message=(
                "Open the browser and authorize with "
                "hello@hiddenova.com."
            ),
            success_message=(
                "Mecoria OS YouTube authorization completed. "
                "You may close this browser tab."
            ),
            open_browser=True,
            access_type="offline",
            prompt="consent"
        )

    TOKEN_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    TOKEN_PATH.write_text(
        credentials.to_json(),
        encoding="utf-8"
    )

    return credentials


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Connect Mecoria OS to the Hiddenova "
            "YouTube channel using Google OAuth."
        )
    )

    parser.add_argument(
        "--expected-channel-id",
        required=True
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    credentials = load_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False
    )

    response = youtube.channels().list(
        part="id,snippet",
        mine=True,
        maxResults=50
    ).execute()

    channels = response.get("items", [])

    if not channels:
        raise ValueError(
            "No YouTube channel was returned for "
            "the authorized account."
        )

    print("AUTHORIZED_CHANNELS:")

    for channel in channels:
        print(
            f"- {channel['snippet']['title']} "
            f"({channel['id']})"
        )

    selected = next(
        (
            channel
            for channel in channels
            if channel["id"]
            == args.expected_channel_id
        ),
        None
    )

    if not selected:
        raise ValueError(
            "Hiddenova channel was not found under "
            "the authorized Workspace account."
        )

    analytics = build(
        "youtubeAnalytics",
        "v2",
        credentials=credentials,
        cache_discovery=False
    )

    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    report = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date.isoformat(),
        endDate=end_date.isoformat(),
        metrics=(
            "views,estimatedMinutesWatched,"
            "averageViewDuration"
        )
    ).execute()

    print(
        "SELECTED_CHANNEL_TITLE:",
        selected["snippet"]["title"]
    )
    print(
        "SELECTED_CHANNEL_ID:",
        selected["id"]
    )
    print(
        "ANALYTICS_COLUMN_COUNT:",
        len(report.get("columnHeaders", []))
    )
    print(
        "ANALYTICS_ROW_COUNT:",
        len(report.get("rows", []))
    )
    print(
        "TOKEN_PATH:",
        TOKEN_PATH.relative_to(PROJECT_ROOT)
    )
    print("YOUTUBE_OAUTH_CONNECTION: passed")


if __name__ == "__main__":
    main()
