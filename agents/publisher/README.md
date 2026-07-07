# Publisher Agent

## Purpose

Publisher Agent prepares a structured publishing package for Mecoria Media content.

The first version does not upload to YouTube.

It prepares metadata, asset references, and readiness status.

## Input

agents/script/output/<channel>/latest.json

agents/seo/output/<channel>/latest.json

agents/image_generation/output/<channel>/latest.json

agents/image_qa/output/<channel>/latest.json

core/execution/state/<channel>_image.json

## Output

agents/publisher/output/<channel>/latest.json

agents/publisher/output/<channel>/archive/

## Responsibilities

- Prepare YouTube title
- Prepare YouTube description
- Prepare tags
- Prepare hashtags
- Prepare chapters
- Reference thumbnail image path
- Reference source outputs
- Check publishing readiness
- Block upload if required assets are missing

## Not Responsible For

- YouTube upload
- Video generation
- Script writing
- SEO creation
- Image generation
- Image QA

## Status

Architecture contract ready.