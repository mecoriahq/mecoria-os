# Mecoria OS Integration Layer v1

## Purpose

Mecoria OS must become the operating system of the company, not just a YouTube automation project.

The system should connect:

- GitHub
- Local agent outputs
- Records
- Notion
- n8n
- YouTube
- Future business units

---

## Source of Truth Rules

### GitHub

GitHub is the source of truth for:

- source code
- agent logic
- schemas
- standards
- configs without secrets
- permanent records under `records/`

### Agent Outputs

Agent output folders are runtime outputs.

They should not be committed unless intentionally saved under `records/`.

### Records

The `records/` folder stores intentional business history:

- upload records
- release records
- founder reviews
- channel readiness
- voice decisions
- thumbnail decisions
- sourcing decisions
- license records
- future analytics snapshots

### Notion

Notion is the CEO / operations dashboard.

Notion should display:

- current video status
- agent status
- task status
- channel status
- publishing queue
- analytics snapshots
- decisions needed from founder

Notion should not be the only source of truth.

### n8n

n8n should handle:

- scheduled sync jobs
- API polling
- webhooks
- notification routing
- future recurring workflows

---

## Integration Principle

Do not connect everything directly to everything.

Correct flow:

Agent Output
↓
Record / Registry
↓
Sync Agent
↓
Notion

This keeps the system debuggable and scalable.

---

## First Notion Sync Targets

### 1. YouTube Channels Database

Sync:

- channel name
- launch status
- public video count
- latest video URL
- next action
- health notes

### 2. Publishing Queue Database

Sync:

- video title
- channel
- status
- current pipeline stage
- public URL
- unlisted URL
- upload package path
- release version

### 3. AI Agents Database

Sync:

- agent name
- status
- last run
- next agent
- output path
- source files

### 4. Content Ideas Database

Sync:

- idea title
- channel
- status
- research status
- script status
- priority

### 5. Analytics / Reports Database

Sync later:

- impressions
- views
- CTR
- average view duration
- average percentage viewed
- subscribers gained
- comments
- analysis notes

---

## Notion Sync Rules

- Never sync secrets.
- Never sync local full absolute paths if avoidable.
- Prefer repo-relative paths.
- Sync only intentional records and approved outputs.
- Runtime outputs can be summarized but not treated as permanent truth.
- Failed runs should be visible but not overwrite approved records.
- Founder decisions must be recorded before public publishing changes.

---

## Required Environment Variables

These go in `.env`, never committed:

NOTION_API_KEY=
NOTION_MECORIA_OS_PAGE_ID=
NOTION_PROJECTS_DB_ID=
NOTION_TASKS_DB_ID=
NOTION_BUSINESS_UNITS_DB_ID=
NOTION_AI_AGENTS_DB_ID=
NOTION_KNOWLEDGE_HUB_DB_ID=
NOTION_YOUTUBE_CHANNELS_DB_ID=
NOTION_PUBLISHING_QUEUE_DB_ID=
NOTION_CONTENT_IDEAS_DB_ID=
NOTION_ANALYTICS_DB_ID=

---

## Build Order

1. Create integration architecture.
2. Create Notion mapping config.
3. Create agent registry scanner.
4. Create Notion sync dry-run agent.
5. Add Notion credentials locally.
6. Test sync with one database only.
7. Expand sync to Publishing Queue and AI Agents.
8. Add n8n scheduled sync later.

---

## Current Priority

During the first 24 hours after Hiddenova launch, do not over-edit the public video.

Use the waiting window to build the operating system layer.
