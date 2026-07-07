# Image Prompt Agent

## Purpose

Image Prompt Agent converts Visual Brief output into provider-specific image generation prompts.

It does not generate images.

## Input

agents/visual_brief/output/<channel>/latest.json

agents/qa/output/<channel>/latest.json

## Output

agents/image_prompt/output/<channel>/latest.json

agents/image_prompt/output/<channel>/archive/

## Providers

- OpenAI
- Flux
- Midjourney

## Responsibilities

- Create OpenAI image prompt
- Create Flux image prompt
- Create Midjourney image prompt
- Preserve visual brief intent
- Keep provider logic separate from visual strategy

## Not Responsible For

- Image generation
- Visual strategy
- SEO metadata
- Script writing
- Publishing

## Status

Architecture contract ready.