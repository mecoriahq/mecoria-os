# Fact-Risk Repair Target Guard

## Problem

A model-generated Fact/Risk QA result may refer to a narration location
that does not exist in the current best script candidate, such as
`main_sections[7].narration` when the script has only seven sections.

## Policy

Before section repair:

- validate every repair location against the current canonical script
- relocate an issue when its exact statement exists in one unique block
- discard an issue as stale when the statement is not present anywhere
- never call the repair model with an out-of-range location
- never raise an index error for a model-generated location

If all QA targets are stale, the old QA result is invalidated and a fresh
Fact/Risk QA pass is requested against the current script.
