Image Prompt Agent Workflow

1. Read the latest Visual Brief Agent output.
2. Read the latest QA Agent output.
3. Continue only if QA status is approved.
4. Convert the visual brief into provider-specific prompts.
5. Create an OpenAI image prompt.
6. Create a Flux image prompt.
7. Create a Midjourney image prompt.
8. Return only valid JSON following the schema.