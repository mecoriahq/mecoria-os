# Hybrid Capacity Contract v1

## Goal

Use one deterministic capacity calculation for:

1. Video Stock QA
2. Media Orchestrator pre-render validation
3. Hybrid Video Assembly

This prevents a stock package from passing QA and later failing during
assembly because a different component used different duration math.

## Shared Engine

`core/hybrid_capacity.py`

The engine converts timeline values to integer frames at 30 FPS. It owns:

- stock segment placement
- non-overlapping stock capacity
- AI image minimum and maximum capacity
- AI image reuse limits
- AI video duration
- narration plus tail-padding target
- exact deficit frames and seconds
- estimated additional stock clip count

## Controlled Repair

When capacity is insufficient:

```text
STATUS: visual_capacity_repair_required
NEXT_AGENT: video_stock_pipeline
HYBRID_CAPACITY_DEFICIT_SECONDS: <exact deficit>
ESTIMATED_ADDITIONAL_STOCK_CLIPS: <estimate>
STACK_TRACE: false
```

No render starts. Existing audio and AI assets are reused.

## Safety

- stock overlap remains blocked
- stock looping remains blocked
- cross-video asset reuse remains blocked
- channel-specific quality gates remain active
- visual pacing QA remains active
- defensive assembly validation remains active

## Regression Fixtures

- Hiddenova `video_006` must pass.
- Rise Dossier `video_001` must pass with the current 13-second limit.
- The historical Rise Dossier 12-second capacity configuration must fail.
- Stock QA and assembly must consume the same shared capacity report.

## Exact Frame Allocation

The capacity report exposes exact selected frame counts for stock and AI
images. Assembly materializes those frame counts directly. It never converts
selected frames to rounded decimal seconds and back to frames.

This prevents a repeating decimal such as `242.566667` seconds from being
rounded upward by one frame during allocation after the same package was
already approved.

The contract invariant is:

```text
report approved
=> selected stock frames materialize exactly
=> selected AI image frames materialize exactly
=> assembly receives the same approved plan
```
