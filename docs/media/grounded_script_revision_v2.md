# Grounded Script Revision v2

## Problem

A factual script can fail Fact/Risk QA and then become too short after
unsupported language is removed. A separate word-count retry must not
reintroduce the same unsupported wording merely to restore length.

## Combined Revision

The revision controller now treats these as simultaneous requirements:

- preserve every Fact/Risk QA correction
- keep all flagged statements and equivalent implications out
- use only approved claim IDs
- keep allegations attributed
- land near the middle of the approved word-count range
- use section-level word targets

## Safe Expansion

Allowed expansion sources:

- approved claim detail
- approved dates and chronology
- approved source attribution
- documented comparisons
- documented consequences

Blocked expansion sources:

- generic medical or legal explanation
- invented motive or causation
- secrecy, collapse, credibility, or psychology language not in claims
- negative legal conclusions about people
- quarantined claims
- dramatic filler

## Rise Dossier Target

- approved range: 1325-1550 narration words
- internal revision target: approximately 1438 words
- maximum automatic attempts: 2
