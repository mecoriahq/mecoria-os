import unittest
import warnings
from pathlib import Path


class RunnerSyntaxContractTests(unittest.TestCase):
    def test_mecoria_media_has_no_syntax_warnings(self):
        root = Path(__file__).resolve().parents[1]
        source_path = (
            root / "scripts" / "mecoria_media.py"
        )
        source = source_path.read_text(
            encoding="utf-8-sig"
        )

        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                SyntaxWarning,
            )
            compile(
                source,
                str(source_path),
                "exec",
            )


if __name__ == "__main__":
    unittest.main()
