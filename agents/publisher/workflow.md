Publisher Agent Workflow

1. Read the latest Script Agent output.
2. Read the latest SEO Agent output.
3. Read the latest Image Generation Agent output.
4. Read the latest Image QA Agent output.
5. Read the latest Execution Context state.
6. Continue only if Image QA status is approved.
7. Continue only if Execution Context next_agent is publisher.
8. Create a structured YouTube publishing package.
9. Mark metadata and thumbnail readiness.
10. Mark video readiness as false until video generation exists.
11. Return only valid JSON following the schema.