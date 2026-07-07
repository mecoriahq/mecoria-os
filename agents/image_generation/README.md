# Image Generation Agent

## Purpose

Image Generation Agent creates an actual image file from Image Prompt Agent output.

The first production version uses OpenAI as the provider.

## Input

agents/image_prompt/output/<channel>/latest.json

## Output

agents/image_generation/output/<channel>/latest.json

agents/image_generation/output/<channel>/archive/

agents/image_generation/output/<channel>/images/

## Responsibilities

- Read Image Prompt output
- Select provider
- Generate image
- Save image file
- Save generation metadata

## Not Responsible For

- Visual strategy
- Image prompt writing
- SEO metadata
- Script writing
- Publishing

## Status

Architecture contract ready.