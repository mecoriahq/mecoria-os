# QA Agent

## Purpose

QA Agent acts as the quality gate for Mecoria Media.

It reviews Script Agent and SEO Agent outputs before the pipeline continues to Thumbnail Agent.

## Input

agents/script/output/<channel>/latest.json

agents/seo/output/<channel>/latest.json

## Output

agents/qa/output/<channel>/latest.json

agents/qa/output/<channel>/archive/

## Responsibilities

- Evaluate script quality
- Evaluate SEO alignment
- Detect weak titles
- Detect poor descriptions
- Detect weak tags or keywords
- Detect weak thumbnail text
- Approve or reject pipeline continuation
- Provide structured issues and recommendations

## Not Responsible For

- Writing scripts
- Creating SEO metadata
- Creating thumbnail prompts
- Publishing videos

## Status

Architecture contract ready.