# Deterministic Factual Repair v1.1

## Purpose

Mecoria Media must not pause for founder review when every remaining factual issue has a safe, exact, machine-verifiable correction.

This layer runs after the normal AI section-repair budget is exhausted. It does not replace factual research, the claims ledger, Fact QA, Risk Review, or founder judgment.

## Safe Automatic Actions

Only the following actions are allowed:

- `remove_exact_text`
- `add_claim_id`

Text actions first require an exact or normalized-exact match in the declared script block. When a preserved candidate has minor wording drift, the engine may remove one unique full sentence only when all of these conditions pass:

- the QA instruction explicitly allows removal or qualification;
- the statement is at least 12 words;
- the first 8 normalized words match;
- the last 6 normalized words match;
- similarity is at least 0.72;
- exactly one sentence matches.

Each claim ID must already be present in `approved_claim_ids`. The engine never invents replacement facts from free-form QA guidance.

## Founder Review Boundary

Founder factual review remains required when:

- a high-risk issue exists;
- an approved supporting claim is unavailable;
- the requested edit is ambiguous;
- neither an exact nor a unique anchored full-sentence target can be located;
- deterministic claim-reference validation fails;
- the same repair signature repeats;
- the bounded deterministic repair budget is exhausted.

## Flow

```text
Fact QA rejected
-> normal section repair attempts
-> structured deterministic repair plan
-> exact or anchored-sentence repair validation
-> canonical script update
-> SEO and Fact QA rerun
-> founder review only if unresolved
```

## Safety Rules

- The repair engine is bounded, idempotent, and requires a unique match.
- It changes only `narration` and `claim_ids`.
- It validates the repaired script against the approved claims ledger.
- It does not call OpenAI by itself.
- It does not render, upload, publish, commit, or push.
- Automatic video approval never means automatic public release.

## Fact QA anchoring contract

Fact QA unsupported statements must be copied verbatim from the current
narration block. Paraphrased or prior-draft statements are treated as a QA
contract failure, not as script defects. The agent receives one automatic
content-contract retry. If the second response is still unanchored, the run
enters the controlled model-retry checkpoint instead of founder review.

A stale or unanchored QA item may be excluded from a deterministic repair plan
only when at least one separate current-script issue has a whitelisted exact
action. The script is never approved from that exclusion; SEO and Fact QA are
invalidated and rerun after the exact repair.
