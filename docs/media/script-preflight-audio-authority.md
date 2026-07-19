# Script Preflight and Audio Duration Authority

## Decision

Narration word count is a preflight estimate. Actual TTS audio duration is
the final runtime authority.

A factual script must not be forced to add unsupported language only to
reach a fixed word minimum before the audio system measures the real voice.

## Rise Dossier Policy

- target script range: 1325-1550 words
- absolute pre-audio floor: 1100 words
- dynamic pre-audio floor: 85 percent of the current target minimum
- actual audio target: 540-630 seconds
- scripts above the pre-audio floor may continue provisionally
- scripts below the floor remain blocked
- scripts above the maximum remain blocked
- Fact/Risk QA must still pass before audio generation
- actual TTS duration may trigger a bounded script revision

## Gate Order

```text
Script target-word attempts
→ pre-audio gate
→ Fact/Risk QA
→ editorial QA
→ TTS generation
→ actual audio duration gate
```

## Safety

A provisional word-count result does not waive factual, editorial, audio,
or founder approval gates. It only prevents the word estimate from blocking
the existing actual-duration feedback loop.
