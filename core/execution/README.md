# Execution Context

## Purpose

Execution Context controls pipeline attempts, revision loops, and next-agent decisions.

It prevents infinite revision cycles and keeps track of quality history.

## Responsibilities

- Track current attempt
- Track maximum attempts
- Track pipeline status
- Track QA scores
- Decide next agent
- Trigger human review when max attempts are reached

## Initial Use Case

Image generation feedback loop:

Image Generation

↓

Image QA

↓

Image Revision

↓

Image Generation

↓

Image QA

## Status

Architecture contract ready.