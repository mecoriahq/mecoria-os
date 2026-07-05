# Mecoria OS

Mecoria OS is the internal operating system for Mecoria.

It manages AI agents, automation workflows, prompts, technical documentation, and reusable systems for building an AI-first company.

## Mission

Build a scalable AI-powered company operating across media, automation, software, e-commerce, and digital products.

## Current Focus

Mecoria Media.

The first goal is to build automated YouTube content systems, starting with Hiddenova.

## Architecture

- Notion: Company OS and operations dashboard
- GitHub: Technical source of truth
- OpenAI: Intelligence layer
- n8n: Automation layer
- Cloudflare: Infrastructure and security
- Google Workspace: Communication and documents

## Repository Structure

- `.github` — GitHub workflows and repository configuration
- `agents` — AI agent definitions and working files
- `assets` — Logos, diagrams, and visual documentation assets
- `configs` — Configuration templates
- `docs` — Technical documentation
- `prompts` — Version-controlled AI prompts
- `scripts` — Automation and setup scripts
- `templates` — Reusable templates
- `tests` — Test files and validation scripts
- `workflows` — n8n workflow exports

## Engineering Principles

- Build systems, not manual processes.
- Every repetitive task should become an automation.
- Keep the architecture simple but scalable.
- Use GitHub as the source of truth for technical assets.
- Use Notion as the operating system for company management.
- Never commit secrets or API keys.
- Test before production.

## First Milestone

Research Agent MVP:

Generate 10 high-quality content ideas automatically and write them into the Notion Content Ideas database.

## Status

Phase 2 — Engineering Foundation.