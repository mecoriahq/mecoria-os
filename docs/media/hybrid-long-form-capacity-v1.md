# Hybrid Long-Form Capacity v1

## Problem

Rise Dossier video_001 has:

- 547.75 seconds of narration
- 3 seconds of timeline tail padding
- 252.59 seconds of approved, non-reused stock footage
- 12 approved AI images
- at most two motion uses per AI image

The previous AI image limit was 12 seconds per use. Its maximum capacity was:

`12 images × 2 uses × 12 seconds = 288 seconds`

Combined with stock:

`252.59 + 288 = 540.59 seconds`

The required one-cycle timeline is:

`547.75 + 3 = 550.75 seconds`

The package was therefore short by 10.16 seconds even though it had enough
unique stock clips and AI images.

## Change

The maximum AI image segment duration is increased from 12 to 13 seconds.

This provides:

`12 images × 2 uses × 13 seconds = 312 seconds`

The maximum combined capacity becomes 564.59 seconds, enough for the
one-cycle timeline without adding a third image use or repeating stock.

## Safety Preserved

- maximum stock segment duration remains 8 seconds
- maximum uses per AI image remains 2
- one-cycle coverage remains mandatory
- stock clips are not repeated
- oversized timelines still fail
- the change does not regenerate audio or images
