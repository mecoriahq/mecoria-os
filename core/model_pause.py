from __future__ import annotations

from typing import Any

from core.video_run_context import save_context, set_status


CONTROLLED_MODEL_RETRY_STATUS = "model_retry_required"
MODEL_RETRY_RESUMING_STATUS = "model_retry_resuming"


def record_model_retry_pause(
    *,
    context: dict[str, Any],
    agent: str,
    error: BaseException,
) -> dict[str, Any]:
    gates = context.setdefault("quality_gates", {})
    retry_state = gates.setdefault("model_retry_state", {})
    prior_count = int(retry_state.get("pause_count", 0))
    paused_from_status = str(context.get("status") or "")
    paused_from_next_agent = str(
        context.get("next_agent") or ""
    )
    retry_state.update({
        "agent": agent,
        "pause_count": prior_count + 1,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "paused_from_status": paused_from_status,
        "paused_from_next_agent": paused_from_next_agent,
        "resume_in_progress": False,
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


def _normalize_retry_agent(value: Any) -> str:
    agent = str(value or "").strip()

    if not agent:
        return ""

    if not agent.replace("_", "").isalnum():
        return ""

    return agent


def prepare_model_retry_resume(
    *,
    context: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    if str(context.get("status") or "") != (
        CONTROLLED_MODEL_RETRY_STATUS
    ):
        return context, False

    gates = context.get("quality_gates", {})
    retry_state = gates.get("model_retry_state")

    if not isinstance(retry_state, dict):
        print("MODEL_RETRY_RESUME_BLOCKED: missing_retry_state")
        return context, False

    retry_agent = _normalize_retry_agent(
        retry_state.get("agent")
    )
    checkpoint_agent = _normalize_retry_agent(
        context.get("next_agent")
    )

    if not retry_agent:
        print("MODEL_RETRY_RESUME_BLOCKED: invalid_retry_agent")
        return context, False

    if checkpoint_agent and checkpoint_agent != retry_agent:
        print("MODEL_RETRY_RESUME_BLOCKED: agent_mismatch")
        return context, False

    prior_resume_count = int(
        retry_state.get("resume_count", 0)
    )
    retry_state.update({
        "resume_count": prior_resume_count + 1,
        "resume_in_progress": True,
        "last_resumed_agent": retry_agent,
        "last_resume_error_type": str(
            retry_state.get("error_type") or ""
        ),
    })
    context = set_status(
        context=context,
        status=MODEL_RETRY_RESUMING_STATUS,
        next_agent=retry_agent,
    )
    save_context(context)

    print("MODEL_RETRY_RESUME: started")
    print(f"MODEL_RETRY_AGENT: {retry_agent}")
    print(
        "MODEL_RETRY_RESUME_COUNT: "
        f"{retry_state['resume_count']}"
    )
    print("MODEL_RETRY_PRESERVED_OUTPUTS: true")
    print("MODEL_RETRY_STACK_TRACE: false")
    return context, True
