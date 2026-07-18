# Mecoria Media OS v1

## Purpose

Mecoria Media OS is the multi-channel control plane for Mecoria Media.

It does not replace channel agents. It coordinates channel configs, production
eligibility, status reporting, Notion sync, and safe execution.

## Registered Channels

- `hiddenova`: active, production enabled, automatic next-video creation disabled.
- `rise_dossier`: planning, production disabled until brand assets and channel-specific production systems are complete.

## Main Commands

```powershell
python scripts\mecoria_media_os.py status all
python scripts\mecoria_media_os.py run all
python scripts\mecoria_media_os.py run all --execute
python scripts\mecoria_media_os.py sync-notion
python scripts\mecoria_media_os.py sync-notion --apply
python scripts\mecoria_media_os.py bootstrap rise_dossier
```

## Safety Rules

- `run all` is plan-only by default.
- Actual execution requires `--execute`.
- A channel must have `production_enabled: true`.
- Automatic next-video creation must be enabled in channel config.
- Public release remains founder gated.
- Channel assets and content cannot be reused across channels by default.
- No secrets are stored in channel configs.

## Current Operational Decision

Hiddenova Video 6 is paused while the control plane, analytics feedback loop,
and second-channel foundation are built.

Rise Dossier is registered but cannot produce content until these blockers are resolved:

- brand assets
- editorial system
- thumbnail system
- first full dry-run
