import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.video_run_context import (
    resolve_context_input,
)


class ContextInputResolutionTests(unittest.TestCase):
    def test_output_is_preferred_over_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            source_path = root / "source.json"
            output_path = root / "output.json"

            source_path.write_text("{}", encoding="utf-8")
            output_path.write_text("{}", encoding="utf-8")

            context = {
                "sources": {
                    "script": "source.json"
                },
                "outputs": {
                    "script": "output.json"
                }
            }

            with patch(
                "core.video_run_context.PROJECT_ROOT",
                root
            ):
                resolved = resolve_context_input(
                    context=context,
                    key="script"
                )

            self.assertEqual(
                resolved,
                output_path
            )

    def test_source_is_used_as_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "source.json"
            source_path.write_text("{}", encoding="utf-8")

            context = {
                "sources": {
                    "script": "source.json"
                },
                "outputs": {}
            }

            with patch(
                "core.video_run_context.PROJECT_ROOT",
                root
            ):
                resolved = resolve_context_input(
                    context=context,
                    key="script"
                )

            self.assertEqual(
                resolved,
                source_path
            )

    def test_missing_input_is_blocked(self):
        context = {
            "sources": {},
            "outputs": {}
        }

        with self.assertRaises(KeyError):
            resolve_context_input(
                context=context,
                key="script"
            )


if __name__ == "__main__":
    unittest.main()
