# Notion Multi-Channel Sync

## Purpose

The Notion sync pipeline is a Mecoria OS system service. It must not belong to
Hiddenova or any other individual channel.

## Source of Truth

- YouTube Channels: `config/channels/*.json`
- Publishing Queue: `records/run_contexts/<channel>/video_*.json`
- AI Agents: `records/system/agent_registry_latest.json`

Channel-level `latest.json` files are not valid Notion source-of-truth records.

## System Output

All Notion system agents write runtime output to:

```text
agents/<notion_agent>/output/system/latest.json
```

Intentional sync records remain under:

```text
records/system/
```

## Supported Channels

The preview automatically discovers every channel config where:

```json
{
  "integrations": {
    "notion_sync": true
  }
}
```

A specific channel may still be inspected with:

```powershell
python agents\notion_sync_dry_run\run.py --channel rise_dossier
```

The default is all channels.

## Safety

- Dry-run does not write to Notion.
- Apply remains explicit.
- Publishing Queue keys use `channel:video_id`.
- Publishing Queue rows come from video run contexts.
- `publisher_latest` and channel-level `latest.json` are blocked.
- Production enablement is independent from Notion sync.
