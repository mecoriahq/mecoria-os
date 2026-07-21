# Founder Manual Revision Recovery v1

## Problem

A founder/manual editorial revision can improve repetition, pacing, and hook
quality while remaining slightly below factual approval on a small number of
repairable statements.

The previous candidate ranking restored the older 100/100 factual candidate
immediately whenever the manual revision scored below it. The manual version
was therefore deleted before section repair could run, and the pipeline
returned to the same editorial failure.

## Policy

A pending founder/manual revision is preserved when:

- it is the exact archived manual revision, or a descendant in its active
  section-repair chain
- it has no high-risk issue
- it contains actionable fact/risk repair locations
- it has not yet reached factual approval

The orchestrator then runs section-level fact/risk repair on that version.

The older approved factual candidate remains available as a fallback.

## Fallback

The older best candidate is restored when:

- a high-risk issue appears
- the manual candidate has no actionable repair target
- the candidate is unrelated to the active manual revision chain

## Recovery

If an older orchestrator version already restored the factual fallback, the
new policy finds the archived manual candidate by its recorded SHA-256 hash,
restores it, resets the manual repair budget, and resumes section repair.

## Invariants

- high-risk issues never bypass fallback
- unrelated candidates use normal ranking
- approved manual descendants continue to editorial QA
- the best factual candidate is never deleted
- Hiddenova and non-manual production flows keep their existing behavior
