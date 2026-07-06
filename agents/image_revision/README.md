# Image Revision Agent

## Purpose

Image Revision Agent improves image generation prompts when Image QA rejects a generated image.

It creates revised provider-specific prompts using Image QA feedback.

## Input

agents/image_prompt/output/<channel>/latest.json

agents/image_generation/output/<channel>/latest.json

agents/image_qa/output/<channel>/latest.json

## Output

agents/image_revision/output/<channel>/latest.json

agents/image_revision/output/<channel>/archive/

## Responsibilities

- Read original image prompts
- Read Image QA feedback
- Identify rejection reasons
- Revise OpenAI prompt
- Revise Flux prompt
- Revise Midjourney prompt
- Preserve original Visual Brief intent

## Not Responsible For

- Image generation
- Visual strategy
- Publishing
- SEO metadata
- Script writing

## Status

Architecture contract ready.