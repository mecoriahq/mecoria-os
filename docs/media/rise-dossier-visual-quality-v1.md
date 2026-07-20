# Rise Dossier Visual Quality v1

## Objective

Prevent the slow visual rhythm observed in Rise Dossier video_001 from
reappearing in later videos.

The standard is channel-specific. Hiddenova behavior remains unchanged.

## Production Contract

- minimum unique AI images: 22
- minimum unique stock clips: 26
- minimum combined unique visual assets: 48
- minimum approved stock source duration: 300 seconds
- maximum stock segments per clip: 2
- maximum AI image uses: 2
- maximum AI image hold: 8 seconds
- maximum average visual hold: 6.75 seconds
- maximum P95 visual hold: 8 seconds
- minimum gap before an AI image is reused: 90 seconds
- timeline cycles: 1

## Capacity Rationale

At the maximum planned video duration:

- narration: 630 seconds
- tail padding: 3 seconds
- AI capacity: 22 images × 2 uses × 8 seconds = 352 seconds
- required stock capacity: 633 - 352 = 281 seconds
- stock source duration gate: 300 seconds

The asset/use ceiling supports up to 96 timeline entries:

- stock: 26 clips × 2 segments = 52
- AI: 22 images × 2 uses = 44

This supports a theoretical average hold of about 6.6 seconds across a
633-second timeline, below the 6.75-second production gate.

## Execution Rules

- the editorial profile is the source of truth
- generic system defaults cannot overwrite the Rise Dossier profile
- pacing QA runs before rendering
- a failed pacing gate blocks production
- existing Rise Dossier video_001 is not regenerated
- no OpenAI API call is required to install or test this change
