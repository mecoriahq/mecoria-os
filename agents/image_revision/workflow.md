Image Revision Agent Workflow

1. Read the latest Image Prompt Agent output.
2. Read the latest Image Generation Agent output.
3. Read the latest Image QA Agent output.
4. Continue only if Image QA status is rejected.
5. Identify the reasons for rejection.
6. Revise provider-specific prompts to fix the issues.
7. Preserve the original Visual Brief intent.
8. Return only valid JSON following the schema.