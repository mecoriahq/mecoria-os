# Mecoria OS Agent Contract

## Purpose

This document defines the communication standard between all AI agents in Mecoria OS.

Every agent must receive structured input and produce structured output.

---

# Communication Rules

- Agents never communicate using free-form text.
- Agents exchange structured JSON data.
- Every output must be machine-readable.
- Every response must be deterministic whenever possible.

---

# Standard Flow

Research Agent
↓

Script Agent
↓

SEO Agent
↓

Thumbnail Agent
↓

Voice Agent
↓

Video Agent
↓

QA Agent
↓

Publisher Agent

---

# Input Contract

Every agent receives:

- Task
- Context
- Configuration
- Previous Agent Output

---

# Output Contract

Every agent returns:

- Status
- Result
- Metadata
- Errors (if any)

---

# Versioning

Current Version: v1.0

Future changes must remain backward compatible whenever possible.