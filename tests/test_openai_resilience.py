import json
import unittest

from core.openai_resilience import (
    OpenAIRetryExhausted,
    RetryPolicy,
    call_with_retry,
    require_nonempty_text,
)


class OpenAIResilienceTests(unittest.TestCase):
    def test_empty_responses_retry_then_succeed(self):
        attempts = []
        responses = ["", "", '{"ok": true}']

        def operation():
            attempts.append(1)
            value = responses.pop(0)
            return json.loads(
                require_nonempty_text(
                    value,
                    label="test",
                )
            )

        result = call_with_retry(
            operation,
            operation_name="test_operation",
            policy=RetryPolicy(
                max_attempts=3,
                base_delay_seconds=0,
                maximum_delay_seconds=0,
            ),
            sleep=lambda _: None,
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(attempts), 3)

    def test_empty_responses_end_in_controlled_exception(self):
        with self.assertRaises(OpenAIRetryExhausted) as captured:
            call_with_retry(
                lambda: require_nonempty_text(
                    "",
                    label="test",
                ),
                operation_name="test_operation",
                policy=RetryPolicy(
                    max_attempts=3,
                    base_delay_seconds=0,
                    maximum_delay_seconds=0,
                ),
                sleep=lambda _: None,
            )

        self.assertEqual(captured.exception.attempts, 3)

    def test_non_transient_error_is_not_retried(self):
        attempts = []

        def operation():
            attempts.append(1)
            raise TypeError("programming error")

        with self.assertRaises(TypeError):
            call_with_retry(
                operation,
                operation_name="test_operation",
                policy=RetryPolicy(
                    max_attempts=3,
                    base_delay_seconds=0,
                    maximum_delay_seconds=0,
                ),
                sleep=lambda _: None,
            )

        self.assertEqual(len(attempts), 1)

    def test_keyboard_interrupt_is_never_swallowed(self):
        def operation():
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            call_with_retry(
                operation,
                operation_name="keyboard_interrupt_test",
                policy=RetryPolicy(
                    max_attempts=3,
                    base_delay_seconds=0,
                ),
            )


if __name__ == "__main__":
    unittest.main()
