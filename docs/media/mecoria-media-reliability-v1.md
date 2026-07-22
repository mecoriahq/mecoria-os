# Mecoria Media Reliability v1

## Goal

Mecoria Media production must not require a video-specific Python patch
when factual, editorial, word-count, or founder checkpoints are reached.

The founder-facing workflow is limited to:

1. topic approval
2. Storyblocks downloads while the bridge remains manual
3. editorial approval only when bounded automatic stabilization cannot pass
4. final video approval

## Content Stabilization Contract

`core/content_stabilization.py` owns the bounded content-recovery policy.

- content stabilization has a finite step budget
- identical actions with identical inputs cannot repeat indefinitely
- small post-repair word-count gaps are repaired with channel-approved CTA
  sentences
- large word-count gaps still pause for review
- factual and editorial outputs are invalidated after a script mutation
- the same logic is available to the runner and the orchestrator

## Word-Budget Recovery

A section repair may remove unsupported wording and leave an otherwise
approved script slightly below its channel minimum.

When the gap is within the channel's safe limit, the system appends an
approved, non-factual brand CTA sentence and re-runs SEO, Fact/Risk QA,
and Editorial QA.

The system never silently fills a large script deficit.

## Finite Recovery

The orchestrator no longer uses an unbounded content loop.

Each channel profile defines:

- `max_content_stabilization_steps`
- `max_same_signature_attempts`
- `max_safe_word_top_up`
- `safe_word_budget_sentences`

Repeated unchanged recovery decisions produce a controlled founder
checkpoint rather than another agent loop or stack trace.

## Generic Founder Commands

```text
python scripts/mecoria_media.py approve-topic <channel> --video-id <id>
python scripts/mecoria_media.py approve-editorial <channel> --video-id <id>
python scripts/mecoria_media.py approve-video <channel> --video-id <id>
```

Editorial approval is allowed only when Fact/Risk QA is fully approved.
The approval is scoped to one channel/video/run and locked to script,
editorial QA, and Fact/Risk QA hashes.

Final video approval does not make the video public. It only marks the
render as approved for manual upload.

## Regression Fixtures

The reliability tests include:

- Rise Dossier video_001
- Rise Dossier video_002
- Hiddenova video_006

Rise Dossier video_002 specifically verifies automatic recovery from the
1319-word factual-safe checkpoint to the 1325-word production minimum.
