# Rise Dossier Fact-Risk Candidate Repair

## Purpose

Fact/Risk QA revisions must improve the script deterministically instead
of replacing a better candidate with the most recent generation.

## Candidate Policy

Every script evaluated by Fact/Risk QA is archived with:

- complete script
- complete Fact/Risk QA result
- unsupported statement count
- high-risk issue count
- factual grounding score
- risk compliance score

Candidate ranking prioritizes:

1. approved status
2. zero high-risk issues
3. fewer unsupported statements
4. fewer total risk issues
5. higher factual and risk scores

A worse revision cannot replace the best archived candidate.

## Section-Level Repair

When Fact/Risk QA rejects a script:

- only narration blocks named in QA issues are sent for repair
- unaffected script blocks remain byte-for-byte unchanged
- repair output must cover exactly the requested locations
- repaired blocks may use only approved claim IDs
- deterministic claim-reference validation runs before the script is saved
- the pre-audio script gate still applies

## Repair Budget

Rise Dossier allows up to three section-level Fact/Risk repair attempts.
This budget is separate from general editorial QA revision attempts.

If the repair budget is exhausted:

- the best candidate remains restored
- the pipeline stops
- no weaker candidate proceeds
- no video or public release is produced

## Theranos Stabilization Fixture

The first Rise Dossier production run exposed a regression:

- one candidate reached 5 unsupported statements
- a later full-script revision regressed to 16 unsupported statements
- the previous implementation overwrote the better candidate

The Theranos candidate-repair fixture permanently tests that the
5-issue candidate ranks above the 16-issue candidate and that only
flagged sections are selected for repair.
