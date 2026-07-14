# Mecoria OS - n8n Manual Trigger Preparation

## Purpose

This document prepares Mecoria OS Notion Sync Runner for a future n8n manual trigger workflow.

This sprint does not install n8n and does not create a live n8n workflow.

The goal is to define the safe command, success checks, failure rules, and notification policy.

## Runner Wrapper

Wrapper path:

scripts/notion_os_sync_runner.ps1

Dry-run command:

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notion_os_sync_runner.ps1

Apply command:

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notion_os_sync_runner.ps1 -Apply

## Success Signals

Dry-run success requires:

- MECORIA_NOTION_SYNC_STATUS: os_sync_dry_run_ready
- MECORIA_NOTION_SYNC_FAILED_STEPS: 0
- MECORIA_NOTION_SYNC_RESULT: ok

Apply success requires:

- MECORIA_NOTION_SYNC_STATUS: os_sync_passed
- MECORIA_NOTION_SYNC_FAILED_STEPS: 0
- MECORIA_NOTION_SYNC_RESULT: ok

## First n8n Workflow Recommendation

Start with manual trigger only.

Do not schedule this workflow yet.

Recommended first workflow:

Manual Trigger -> Execute Command -> Check Success -> Notify On Failure

## Execute Command Node

Use the dry-run command first:

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notion_os_sync_runner.ps1

After manual verification, switch to apply command:

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notion_os_sync_runner.ps1 -Apply

## Failure Policy

If the command exits with a non-zero code, stop the workflow.

Do not retry automatically in the first version.

Notify the founder only on failure.

The notification should include:

- workflow name
- command mode
- failed step count
- runner status
- timestamp

## Safety Rules

- Never expose .env in n8n logs.
- Never paste API keys into n8n notes.
- Never commit .env.
- Start with manual trigger only.
- Add schedule only after the media pipeline is stable.
- Do not add automatic retries yet.

## Future Schedule

Later schedule option:

Daily sync after all media agents are stable.

For now, use manual trigger only.

## Current Status

AI Agents sync is complete.
YouTube Channels sync is complete.
Publishing Queue sync is complete.
Central Notion OS Sync Runner is complete.
Operating procedure is documented.

Next step:

Create the actual n8n manual trigger workflow.
