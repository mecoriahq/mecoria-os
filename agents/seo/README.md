# SEO Agent

## Purpose

SEO Agent generates YouTube SEO metadata from the latest Script Agent output.

The agent is responsible only for search optimization.

It does not modify or rewrite the script.

---

## Input

agents/script/output/<channel>/latest.json

---

## Output

agents/seo/output/<channel>/latest.json

agents/seo/output/<channel>/archive/

---

## Responsibilities

- Generate optimized YouTube title
- Generate description
- Generate SEO keywords
- Generate tags
- Generate hashtags
- Generate thumbnail text
- Generate chapters
- Estimate SEO quality score

---

## Workflow

Script Agent

↓

SEO Prompt

↓

OpenAI

↓

Schema Validation

↓

latest.json

↓

archive

---

## Run

```bash
python agents/seo/run.py
```

---

## Status

Production