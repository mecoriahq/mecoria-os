# Founder Manual Revision Lineage v1

## Problem

The first recovery contract preserved the exact founder-authored script only at
the start of factual repair. A section-repair descendant could lose the source
reference used to identify the founder lineage. When that happened, candidate
ranking treated the repaired descendant as unrelated and restored the older
100/100 factual candidate.

The observed Boeing video_002 sequence was:

1. founder candidate 17 recovered
2. two factual sections repaired
3. repaired descendant reached 98 factual / 100 risk with one unsupported item
4. descendant was treated as unrelated
5. candidate 6 was restored
6. the pipeline returned to the repetition-risk loop

## Contract

A founder manual revision now owns a bounded lineage across the complete
factual stabilization phase.

- the exact founder candidate activates the lineage
- section-repair descendants remain inside the lineage
- zero high-risk issues plus actionable unsupported statements trigger another
  bounded section repair
- any high-risk issue still triggers the safe factual fallback
- factual approval keeps the lineage active until editorial evaluation
- an editorial failure pauses for founder review with the current candidate
  preserved
- generic automatic editorial repair is blocked for the founder lineage
- the lineage ends only after editorial approval or an explicit safety fallback

## Safety

- the existing best factual candidate remains available as fallback
- unrelated candidates continue to use standard ranking
- Hiddenova behavior is unchanged
- no global quality threshold is reduced
- no runtime context is changed by the installation patch
