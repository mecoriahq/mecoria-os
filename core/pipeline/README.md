# Mecoria Media Pipeline

## Purpose

The Media Pipeline orchestrates Mecoria Media production agents.

It will eventually allow the full content process to run from a single command.

## Pipeline Order

Research

↓

Script

↓

SEO

↓

QA

↓

Visual Brief

↓

Image Prompt

↓

Image Generation

↓

Image QA

↓

Image Revision if needed

↓

Publisher

## Responsibilities

- Define pipeline execution order
- Track step status
- Stop on failure
- Respect Execution Context
- Prevent infinite revision loops
- Save pipeline run metadata

## Not Responsible For

- Creating agent outputs directly
- Replacing individual agents
- Uploading to YouTube
- Editing agent logic

## Status

Architecture contract ready.