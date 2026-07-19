from __future__ import annotations

from typing import Any

from core.video_run_context import save_context, set_status


CONTROLLED_MODEL_RETRY_STATUS = "model_retry_required"


def record_model_retry_pause(
    *,
    context: dict[str, Any],
    agent: str,
    error: BaseException,
) -> dict[str, Any]:
    gates = context.setdefault("quality_gates", {})
    retry_state = gates.setdefault("model_retry_state", {})
    prior_count = int(retry_state.get("pause_count", 0))
    retry_state.update({
        "agent": agent,
        "pause_count": prior_count + 1,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "preserved_outputs": sorted(
            context.get("outputs", {}).keys()
        ),
    })
    context = set_status(
        context=context,
        status=CONTROLLED_MODEL_RETRY_STATUS,
        next_agent=agent,
    )
    save_context(context)

    print("MODEL_RETRY_CONTROLLED_PAUSE: true")
    print(f"MODEL_RETRY_AGENT: {agent}")
    print("MODEL_RETRY_PRESERVED_OUTPUTS: true")
    print("MODEL_RETRY_STACK_TRACE: false")
    return context
