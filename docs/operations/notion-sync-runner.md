# Mecoria OS - Notion Sync Runner Operating Procedure

## Purpose

This document explains how Mecoria OS syncs operational data from GitHub records and agents into Notion dashboards.

The Notion OS Sync Runner is the central command for refreshing the first Mecoria Media operational dashboards.

Current synced Notion databases:

- AI Agents
- YouTube Channels
- Publishing Queue

## Source of Truth

Notion is not the source of truth.

The source of truth is:

- GitHub repository
- records/
- agents/
- docs/

Notion is only the dashboard layer.

## Main Runner

Runner path:

agents/notion_os_sync_runner/run.py

Dry-run command:

python agents\notion_os_sync_runner\run.py

Apply command:

python agents\notion_os_sync_runner\run.py --apply

## Runner Steps

The runner executes five steps:

1. Notion connection test
2. Notion sync preview refresh
3. AI Agents sync
4. YouTube Channels sync
5. Publishing Queue sync

## Expected Dry-Run Status

Expected main status:

os_sync_dry_run_ready

Expected child statuses:

- notion_connection_test -> connection_ready
- notion_sync_preview -> preview_ready
- ai_agents_sync_dry_run -> dry_run_ready
- youtube_channels_sync_dry_run -> dry_run_ready
- publishing_queue_sync_dry_run -> dry_run_ready

## Expected Apply Status

Expected main status:

os_sync_passed

Expected child statuses:

- notion_connection_test -> connection_ready
- notion_sync_preview -> preview_ready
- ai_agents_sync -> full_sync_passed
- youtube_channels_sync -> sync_passed
- publishing_queue_sync -> sync_passed

## Safety Rules

- Never commit .env.
- Never paste API keys or tokens into ChatGPT.
- Always run dry-run before apply when sync logic changes.
- Notion is not the technical source of truth.
- Manual Notion rows must not be deleted automatically.
- Manual management agents and GitHub technical agents are different layers.

## Manual Agents

Manual agents are management and operating model agents.

Examples:

- CEO Agent
- COO Agent
- CTO Agent
- CFO Agent
- CMO Agent
- Media Manager

## GitHub Technical Agents

GitHub technical agents are pipeline and automation agents.

Examples:

- research
- script
- seo
- qa
- video_assembly
- publisher
- notion_os_sync_runner

For GitHub synced agents:

- Sync Source = GitHub
- System Key = agent folder name

## Standard Operating Procedure

Step 1 - run dry-run:

python agents\notion_os_sync_runner\run.py

Continue only if the status is:

os_sync_dry_run_ready

Step 2 - run apply:

python agents\notion_os_sync_runner\run.py --apply

Continue only if the status is:

os_sync_passed

Step 3 - check Git:

git status

If records changed and sync passed, commit and push.

## Troubleshooting

401 or connection_failed means the Notion token should be checked.

404 or object_not_found means the database may not be shared with the Mecoria OS connection.

Provided ID is a page not a database means the real database ID must be found.

unmapped_field_count greater than 0 means schema patch is required before apply.

failed_apply_count greater than 0 means failed results must be inspected before rerunning.

## n8n Preparation

This runner will later be connected to n8n.

Recommended first automation:

Manual trigger -> Run Notion OS Sync Runner -> Check os_sync_passed -> Notify only if failed.

Do not schedule daily automation until the media pipeline is more stable.

## Current Status

- AI Agents sync complete
- YouTube Channels sync complete
- Publishing Queue sync complete
- Central Notion OS Sync Runner complete

Next sprint:

Sprint 26K - n8n manual trigger preparation
