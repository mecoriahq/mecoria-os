# Mecoria Agent Schema v1.0

## Purpose

This document defines the standard input and output format for every Mecoria OS Agent.

All agents must follow this schema to ensure compatibility, automation and scalability.

---

# Input Schema

Every agent receives:

```json
{
  "agent": "",
  "channel": "",
  "input": {}
}
```

---

# Output Schema

Every agent returns:

```json
{
  "agent": "",
  "status": "success",
  "data": {}
}
```

---

# Rules

- Always return structured data.
- Never invent missing fields.
- Use clean English.
- Output must be machine-readable.
- Keep field names consistent.
- Do not change schema versions without approval.

---

# Version

Current Version:

v1.0