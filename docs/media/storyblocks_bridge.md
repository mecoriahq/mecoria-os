# Storyblocks Bridge V1

## Goal

Use the existing Storyblocks subscription as Mecoria Media's primary stock provider without scraping the Storyblocks website or requiring Storyblocks API access.

## Founder command

```powershell
python scripts\mecoria_media.py run hiddenova
```

When a video reaches `stock_source_required`, the runner:

1. Builds six video-specific Storyblocks search groups from the approved script.
2. Opens each official Storyblocks footage search in order.
3. Asks the founder to download five unique horizontal clips.
4. Detects only the new files in the Windows Downloads folder.
5. Copies and renames the clips into the video-specific stock workspace.
6. Adds deterministic role prefixes for reliable classification.
7. Builds and attaches the Storyblocks license/source manifest.
8. Resumes stock QA, hybrid assembly, video QA, and publishing preparation.

## Manual work remaining

The founder only selects and downloads Storyblocks clips. File movement, naming, duplicate protection, role assignment, manifest creation, and pipeline resume are automatic.

## Resume behavior

The bridge is resumable. Completed search groups are skipped. If the process is stopped, run the same founder command again.

## Safety

- No browser scraping.
- No Storyblocks credentials are stored.
- No Storyblocks API is called.
- Downloaded media stays under `assets/stock/`, which is gitignored.
- Agent outputs stay under `agents/storyblocks_bridge/output/`, which is gitignored.
- Cross-video hash reuse remains blocked by the asset registry.
- Existing video contexts are not modified during installation.
