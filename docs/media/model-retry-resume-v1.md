# Model Retry Resume v1

## Purpose

Prevent a resumable model-rate-limit checkpoint from immediately pausing again before the failed agent is retried.

## Behavior

- A model failure still records `model_retry_required` and stops the current orchestrator invocation.
- The next explicit `--resume` invocation validates the stored failed agent.
- The checkpoint changes to `model_retry_resuming` before the general controlled-pause gate.
- Existing outputs remain intact, so only the first missing or failed agent runs again.
- An invalid or mismatched retry agent keeps the checkpoint paused.
- Repeated calls are idempotent after the status has changed.

## Safety

The resume path does not call OpenAI by itself. It only reopens the checkpoint. Normal agent execution and existing retry limits remain responsible for external model calls. Founder review states and production-quality gates are unchanged.
