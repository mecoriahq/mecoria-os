# Storyblocks Relevance and Timeline Coverage Fix v1

## Purpose

Prevent two production failures:

1. Storyblocks role prefixes being treated as proof of visual relevance.
2. A one-cycle timeline failing even when unused non-overlapping stock duration can cover the narration.

## Relevance Rules

- The Storyblocks role prefix is routing metadata only.
- Original Storyblocks filenames must contain topic-specific evidence from the locked search query and visual direction.
- Generic stock terms such as `truck`, `road`, `warehouse`, `hydraulic`, and `conveyor` are not sufficient by themselves.
- Irrelevant existing clips are moved to a video-specific quarantine folder.
- Approved legacy clips are renamed to the video-specific catalog role before stock ingest.
- The stock ingest agent rejects bridge prefixes that do not match the active role catalog.

## Repair Command

```powershell
python agents\storyblocks_bridge\run.py --channel hiddenova --video-id video_005 --repair
```

Repair mode:

1. Audits existing Storyblocks clips.
2. Quarantines low-relevance clips.
3. Reopens only incomplete search groups.
4. Imports replacements with the correct catalog role.
5. Rebuilds the stock source manifest.
6. Rebuilds stock QA and stock outputs.

## Timeline Coverage Rules

- `maximum_stock_segments_per_clip` remains enforced.
- Stock segments remain non-overlapping.
- Normal stock segment duration remains 6 seconds.
- Existing segments may expand deterministically up to 8 seconds when needed.
- Expansion is distributed across available segments.
- Timeline coverage includes the 3-second tail requirement.
- No second timeline cycle is allowed when `maximum_timeline_cycles` is 1.
- The gate still fails when unique source duration cannot cover the timeline without overlap or reuse.

## Safety

- No API calls are added.
- No browser scraping is added.
- No render is started by the patch installer.
- No commit or push is performed by the patch installer.
- Existing source files are backed up before code replacement.
