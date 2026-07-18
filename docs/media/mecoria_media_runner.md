# Mecoria Media Runner

## Goal

Run the Hiddenova production system through one founder-facing entry point.

```powershell
python scripts\mecoria_media.py run hiddenova
```

The runner uses the video run context as the single source of truth. It never uses `latest.json` as a production input and never creates Git commits or pushes.

## Commands

Start the next video or resume the only active video:

```powershell
python scripts\mecoria_media.py run hiddenova
```

Approve the selected topic and continue automatically:

```powershell
python scripts\mecoria_media.py approve-topic hiddenova
```

Show the current checkpoint:

```powershell
python scripts\mecoria_media.py status hiddenova
```

Target a specific video when needed:

```powershell
python scripts\mecoria_media.py run hiddenova --video-id video_005
```

Attach an approved stock manifest during the temporary stock-source phase:

```powershell
python scripts\mecoria_media.py run hiddenova `
--video-id video_005 `
--stock-manifest records/path/to/manifest.json
```

## Automatic behavior

- Creates the next sequential `video_id` when no active video exists.
- Resumes the only active video automatically.
- Stops at founder topic approval.
- Continues automatically after topic approval.
- Stops at the current stock-source gate until visual acquisition automation is built.
- Stops at final founder video review.
- Blocks ambiguous execution when multiple active contexts exist.
- Uses a per-channel runner lock to prevent concurrent production runs.
- Leaves all Git commit and push decisions manual.

## Founder actions

During the current rollout, the founder performs only:

1. Topic approval.
2. Final video approval.

The stock-source gate remains temporary and will be removed by the next visual automation milestone.
