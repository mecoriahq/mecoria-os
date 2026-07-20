# Effective Content Approval

Production agents must not interpret the raw editorial QA status directly.

The effective content approval rule is:

1. Accept a normal QA result when `status == approved`.
2. Otherwise accept only a cryptographically validated founder editorial
   override for the exact channel, video, run, script, QA, factual QA, and
   editorial candidate.
3. Reject missing, stale, changed, unsafe, or cross-video approvals.

The raw QA output remains immutable. A founder override does not rewrite a
rejected QA result into an approved result.

`video_visual_pipeline` uses this rule before generating visual assets.

## Downstream rule

After `effective_content_approval` returns approved, downstream agents must not
re-check the raw editorial QA status or score. A founder override intentionally
permits a locked factual-safe candidate whose raw editorial result remains
rejected for auditability.

Specialized later-stage gates remain independent and mandatory:

- audio QA
- visual asset QA
- image QA
- video QA
- publisher readiness

Those checks validate generated production assets, not the source script's
editorial approval.
