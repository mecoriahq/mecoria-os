# Hiddenova Thumbnail System v3

## Purpose

Produce high-CTR Hiddenova thumbnails without repeating the same weak concept or requiring routine founder repair.

## Production Contract

Every new video must generate exactly three meaningfully different thumbnail concepts:

1. `scale_and_consequence`
2. `failure_or_risk`
3. `hidden_mechanism`

The concepts must use different headlines and different dominant subjects. Small prompt variations of the same scene are not allowed.

## Candidate Pipeline

1. Generate structured concepts.
2. Run deterministic preflight scoring.
3. Reject incomplete or generic concepts before image generation.
4. Generate one background and one rendered thumbnail for each approved concept.
5. Run multimodal QA against the actual rendered image.
6. Combine preflight and vision scores.
7. Reject candidates below the quality threshold.
8. Record the top two approved finalists.
9. Select the highest-scoring approved candidate.
10. Export only the selected thumbnail.

## Quality Gates

- candidate count: `3`
- finalist count: `2`
- minimum preflight score: `85`
- minimum vision score: `82`
- minimum final score: `85`
- mobile-readable headline: required
- dominant topic-specific subject: required
- clear tension or consequence: required
- clean cinematic composition: required
- generic stock-poster appearance: rejected
- founder review scope: finalists only

## Source of Truth

- standard config: `config/media/hiddenova_thumbnail_standard.json`
- rules config: `config/thumbnail_rules/hiddenova.json`
- gold reference: `config/media/reference_assets/hiddenova_cinematic_v2_gold.png`
- runtime candidate record: `thumbnail_candidates.json`
- final thumbnail record: `thumbnail.json`

The existing gold reference asset is preserved. Version 3 changes the concept, scoring, and selection system rather than replacing the approved layout reference.

## Safety

Thumbnail v3 does not change public videos automatically. It runs inside the video-specific visual pipeline and preserves `channel`, `video_id`, and `run_id` isolation.
