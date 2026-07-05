# Mecoria OS Folder Structure

## Purpose

Define the official folder structure for Mecoria OS to ensure consistency, scalability and maintainability.

---

# Root Structure

```
mecoria-os/
│
├── agents/
├── assets/
├── configs/
├── core/
├── docs/
├── prompts/
├── scripts/
├── templates/
├── tests/
├── workflows/
│
├── .env
├── .gitignore
├── LICENSE
└── README.md
```

---

# Agents

Contains every AI agent.

Each agent must follow the same template.

Example:

```
agents/
    research/
    script/
    seo/
    thumbnail/
    publisher/
```

---

# Core

Shared Python modules.

No business logic.

Reusable only.

---

# Configs

Shared configuration files.

---

# Docs

Company documentation.

Architecture.

Business documentation.

Standards.

---

# Prompts

Reusable prompt components.

---

# Scripts

Development and automation scripts.

---

# Templates

Reusable templates.

---

# Tests

Unit and integration tests.

---

# Workflows

Workflow definitions shared across agents.

---

## Rule

Every new feature must belong to one existing folder.

Avoid creating unnecessary top-level directories.