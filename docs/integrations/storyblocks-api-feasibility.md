# Storyblocks API Feasibility for Mecoria OS

## Purpose

Mecoria Media needs realistic stock footage to avoid slideshow-style videos.

The long-term goal is to let Mecoria OS automatically search stock footage platforms based on the visual asset plan, score candidate clips, save them to the sourcing tracker, and prepare approved assets for video assembly.

---

## Current Decision

Storyblocks is a strong first candidate for stock footage automation because it offers a stock media API and a large stock video library.

However, API integration should not block the first public Hiddenova video.

We will support two workflows:

1. Manual workflow for speed
2. API workflow for scale

---

## Manual Workflow

Use this for the first public-quality Hiddenova rebuild.

Steps:

1. Search Storyblocks manually.
2. Save candidate URLs to the sourcing tracker.
3. Review visual quality, logo risk, label risk, and license status.
4. Download only approved clips.
5. Save local file paths.
6. Use approved footage in video assembly.

Pros:

- fastest
- no API setup delay
- works immediately
- good for learning what quality looks like

Cons:

- not scalable
- manual searching takes time
- repeated work across 5 channels

---

## API Workflow

Use this after the first manual sourcing loop is validated.

Target flow:

Visual Asset Plan
↓
Sourcing Agent
↓
Storyblocks API search
↓
Candidate scoring
↓
Tracker update
↓
Human approval
↓
Licensed download
↓
Video Assembly

---

## Required API Capabilities

The API integration must support:

- search stock video
- filter by query
- get clip metadata
- get preview URLs or thumbnails
- get license/download information
- download approved clips
- save source URL and license record
- save local file path after download

---

## Required Environment Variables

Never commit API credentials to Git.

Expected local `.env` variables:

STORYBLOCKS_API_KEY=
STORYBLOCKS_API_SECRET=
STORYBLOCKS_ACCESS_TOKEN=

Exact credential names may change after reviewing the actual Storyblocks API account setup.

---

## Security Rules

- API keys must only exist in `.env`
- `.env` must stay ignored by Git
- never paste API secrets into commits
- never save paid download tokens in public records
- records may include source URL, asset ID, license status, and local file path
- records must not include private API credentials

---

## Sourcing Agent v0 Scope

The first Sourcing Agent should not download files automatically.

Version 0 should only:

1. read `records/sourcing/hiddenova/stock_broll_tracker.json`
2. find assets with status `not_started`, `candidate_found`, or `searching`
3. search Storyblocks for the asset queries
4. produce candidate results
5. score candidates using quality/risk criteria
6. write suggested candidates to output JSON
7. require human approval before tracker update

No automatic public usage.

---

## Candidate Scoring

Each candidate should be scored on:

- topic relevance
- documentary realism
- motion/usefulness
- visual quality
- logo risk
- readable label risk
- barcode/QR risk
- stock-commercial feeling
- license clarity
- reuse potential

Suggested score:

- 90-100: strong candidate
- 75-89: usable with review
- 60-74: support only
- below 60: reject

---

## Human Approval Rule

Even with API automation, a human must approve footage before public video usage.

Reason:

AI can miss:

- small logos
- readable labels
- barcode details
- private information
- misleading footage
- tone mismatch
- license nuance

---

## First API Test Target

Asset:

A010 - Sorting / Conveyor / Scanner / Warehouse Automation

Search queries:

- automated parcel sorting conveyor scanners warehouse
- logistics warehouse conveyor belt packages moving
- parcel sorting center scanner diverter
- warehouse automation packages conveyor
- package scanning tunnel warehouse robots

Success criteria:

- at least 10 candidates returned
- at least 3 strong candidates above score 80
- source URLs saved
- license status recorded as `needs_account_review`
- no automatic download in v0

---

## Build Order

1. Manual A010 candidate sourcing
2. Manual license/download process
3. First public-quality video rebuild
4. Storyblocks API access check
5. Sourcing Agent v0 dry-run
6. Human approval tracker update
7. Optional automatic download after legal/license process is stable

---

## Current Recommendation

Do not delay the Hiddenova rebuild for API automation.

Use manual sourcing for the first public-quality video.

Build API automation after we validate what usable footage looks like.
