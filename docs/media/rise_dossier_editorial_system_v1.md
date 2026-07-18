# Rise Dossier Editorial System v1

## Purpose

This system produces source-backed 9-10 minute English documentaries
about real companies, founders, public figures, empires, scandals,
and mysteries.

## Channel Flow

```text
research
-> content_idea_selector
-> founder_topic_approval
-> factual_research
-> claims_ledger
-> script
-> seo
-> fact_risk_qa
-> strict_editorial_qa
-> audio_and_visual_production
-> founder_final_review
```

## Factual Standard

- Minimum 8 independent sources.
- Minimum 2 primary sources.
- High-risk claims require at least 2 independent sources.
- Every factual narration block references approved claim IDs.
- Allegations remain attributed.
- Unsupported claims, fabricated quotations, inferred private motives,
  and misleading criminal implications are blocked.
- Fact QA and risk compliance must both score 100 before production.

## Script Standard

- 1325-1550 narration words.
- 540-630 second target duration.
- 5-7 main sections.
- One chronological cause-and-effect narrative spine.
- No mandatory spoken channel-name introduction.
- Concise CTA asks viewers to comment, like, and subscribe.

## Thumbnail Standard

- Standard: `rise_dossier_investigative_v1`.
- Three distinct concepts and two approved finalists.
- Oversized 2-4 word ALL-CAPS headline on the left.
- One dominant recognizable subject on the right.
- Warm white and dossier-red emphasis.
- Premium investigative documentary treatment.
- Fabricated evidence, fake mugshots, fake arrests, fake quotations,
  and unsupported criminal implications are forbidden.

## Safe Validation

```powershell
python scripts\mecoria_media.py run rise_dossier --dry-run
```

The dry-run must not create a video, call production agents, publish,
write to Notion, or enable production.
