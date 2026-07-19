# Automatic Script Word-Count Revision

## Purpose

The Script Agent must not terminate immediately when an otherwise valid
documentary script falls slightly outside the approved narration range.

## Behavior

- Evaluate the first generated script before saving it.
- If it is too short or too long, generate a targeted revision brief.
- Allow at most two automatic word-count revisions.
- Re-evaluate every regenerated script.
- Fail after the configured limit if the script remains outside range.

## Factual Safety

For factual channels such as Rise Dossier:

- revisions may use only approved claim IDs
- revisions cannot introduce new facts
- quarantined claims remain unavailable
- attribution and chronology must remain intact
- the complete script is regenerated and validated

## Current Rise Dossier Configuration

- minimum narration words: 1325
- maximum narration words: 1550
- automatic word-count revision attempts: 2
