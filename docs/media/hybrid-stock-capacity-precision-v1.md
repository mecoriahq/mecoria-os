# Hybrid Stock Capacity Precision v1

## Problem

The hybrid assembler calculated a maximum non-overlapping stock capacity and
then asked the stock expander to reach that exact value.

Both calculations used the same source durations, but the expander treated
exactly 0.01 seconds of remaining capacity as unusable. Across multiple
segments, several valid 0.01-second capacities accumulated into a visible
shortfall and caused a false one-cycle coverage failure.

This was exposed by Hiddenova video_006 even though the approved stock package
contained 26 unique clips and 463.85 seconds of source duration.

## Change

A shared sub-centisecond duration epsilon is used by both stock and AI image
capacity expansion.

Valid 0.01-second residual capacity is now consumed. Real capacity overflow
continues to fail.

## Safety Preserved

- stock segments remain non-overlapping
- source clips are not looped
- cross-video asset reuse remains blocked
- maximum segment durations remain unchanged
- maximum timeline cycles remain unchanged
- no audio, image, stock, or video asset is regenerated
