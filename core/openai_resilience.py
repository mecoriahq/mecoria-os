from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    maximum_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative.")
        if self.maximum_delay_seconds < 0:
            raise ValueError("maximum_delay_seconds cannot be negative.")


class OpenAIRetryExhausted(RuntimeError):
    def __init__(
        self,
        *,
        operation_name: str,
        attempts: int,
        last_error: BaseException,
    ) -> None:
        self.operation_name = operation_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"{operation_name} failed after {attempts} controlled "
            f"attempts: {type(last_error).__name__}: {last_error}"
        )


def require_nonempty_text(
    value: Any,
    *,
    label: str,
) -> str:
    text = str(value or "").strip()

    if not text:
        raise ValueError(f"{label} returned an empty response.")

    return text


def is_transient_model_error(error: BaseException) -> bool:
    if isinstance(error, OpenAIRetryExhausted):
        return False

    if isinstance(error, (TimeoutError, ConnectionError, json.JSONDecodeError)):
        return True

    class_name = type(error).__name__.lower()
    message = str(error).lower()

    transient_class_fragments = (
        "timeout",
        "connection",
        "ratelimit",
        "apierror",
        "internalserver",
        "serviceunavailable",
    )
    transient_message_fragments = (
        "empty response",
        "does not contain valid json",
        "valid json",
        "timed out",
        "timeout",
        "rate limit",
        "connection reset",
        "connection error",
        "temporarily unavailable",
        "server error",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "502",
        "503",
        "504",
    )

    return (
        any(item in class_name for item in transient_class_fragments)
        or any(item in message for item in transient_message_fragments)
    )


def call_with_retry(
    operation: Callable[[], T],
    *,
    operation_name: str,
    policy: RetryPolicy | None = None,
    retry_predicate: Callable[[BaseException], bool] = is_transient_model_error,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, int, BaseException, float], None] | None = None,
) -> T:
    active_policy = policy or RetryPolicy()
    last_error: Exception | None = None

    for attempt in range(1, active_policy.max_attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error

            if (
                attempt >= active_policy.max_attempts
                or not retry_predicate(error)
            ):
                if not retry_predicate(error):
                    raise
                break

            delay = min(
                active_policy.maximum_delay_seconds,
                active_policy.base_delay_seconds * (2 ** (attempt - 1)),
            )

            if on_retry:
                on_retry(
                    attempt,
                    active_policy.max_attempts,
                    error,
                    delay,
                )

            if delay > 0:
                sleep(delay)

    if last_error is None:
        raise RuntimeError(
            f"{operation_name} retry loop ended without a result or error."
        )

    raise OpenAIRetryExhausted(
        operation_name=operation_name,
        attempts=active_policy.max_attempts,
        last_error=last_error,
    )
