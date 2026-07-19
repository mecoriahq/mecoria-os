# Rise Dossier Production Hardening v1

## Locked Invariants

- A Fact/Risk-approved script is immutable as the factual baseline.
- Editorial QA cannot delete the factual baseline or trigger a full-script rewrite.
- Editorial improvements are section-level and limited to current valid blocks.
- A worse factual or editorial candidate cannot replace a better candidate.
- Factually equivalent candidates may continue to editorial evaluation.
- Empty or transient OpenAI responses receive three controlled attempts.
- Retry exhaustion pauses the pipeline and preserves all valid outputs.
- Repair exhaustion requests founder review instead of raising a stack trace.

## Theranos Regression Fixture

The production fixture records the validated Theranos candidate:

- 1341 narration words
- factual grounding 100
- risk compliance 100
- unsupported statements 0
- high-risk issues 0

The remaining editorial improvements are local to hook, introduction,
narrative specificity, and repetition. They must not invalidate factual work.
