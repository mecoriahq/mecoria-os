# Hybrid Stock Capacity Precision v1

## Status

Superseded by `hybrid_capacity_frames_v1`.

## Original Problem

The previous float-based assembler could lose valid residual duration because
capacity checks and expansion used different decimal tolerances. Hiddenova
video_006 exposed this as a false one-cycle coverage failure.

## Current Contract

Hybrid capacity is now calculated in integer frames at the configured timeline
FPS. At 30 FPS, the smallest renderable duration is one frame, approximately
0.033333 seconds. Sub-frame values such as 0.01 seconds are therefore
quantized rather than treated as independently renderable capacity.

The same frame-based calculation is consumed by Stock QA, orchestrator
pre-render validation, and hybrid assembly.

## Safety Preserved

- stock segments remain non-overlapping
- source clips are not looped
- cross-video asset reuse remains blocked
- maximum segment durations remain enforced
- true one-frame overflow continues to fail
- no audio, image, stock, or video asset is regenerated
