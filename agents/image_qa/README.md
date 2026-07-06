# Image QA Agent

## Purpose

Image QA Agent evaluates generated images before they move to publishing.

It checks both technical validity and visual quality.

## Input

agents/image_generation/output/<channel>/latest.json

Generated image file referenced by Image Generation Agent metadata.

## Output

agents/image_qa/output/<channel>/latest.json

agents/image_qa/output/<channel>/archive/

## Responsibilities

- Check image file exists
- Check image file is readable
- Check image format
- Check image size
- Evaluate subject visibility
- Evaluate composition
- Evaluate lighting
- Detect unwanted text
- Detect unwanted logos
- Evaluate alignment with Mecoria Image Generation Standard
- Approve or reject image for publishing

## Not Responsible For

- Image generation
- Image prompt writing
- Visual brief creation
- Publishing

## Status

Architecture contract ready.