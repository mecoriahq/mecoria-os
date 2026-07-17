import importlib.util
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path

from PIL import Image


@contextmanager
def temporary_dependency_stubs():
    names = [
        "openai",
        "dotenv",
        "core.video_run_context",
        "core.asset_usage_registry",
    ]
    previous = {
        name: sys.modules.get(name)
        for name in names
    }

    openai_module = types.ModuleType("openai")
    openai_module.OpenAI = type("OpenAI", (), {})

    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda *args, **kwargs: None

    context_module = types.ModuleType("core.video_run_context")
    for name in [
        "load_context",
        "register_output",
        "resolve_output",
        "resolve_source",
        "save_context",
        "set_status",
    ]:
        setattr(context_module, name, lambda *args, **kwargs: None)

    asset_module = types.ModuleType("core.asset_usage_registry")
    for name in [
        "build_asset_record",
        "register_asset_batch",
        "remove_asset_usage_for_path",
        "validate_asset_batch",
    ]:
        setattr(asset_module, name, lambda *args, **kwargs: None)

    sys.modules["openai"] = openai_module
    sys.modules["dotenv"] = dotenv_module
    sys.modules["core.video_run_context"] = context_module
    sys.modules["core.asset_usage_registry"] = asset_module

    try:
        yield
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_create_thumbnail():
    project_root = Path(__file__).resolve().parent.parent
    module_path = (
        project_root
        / "agents"
        / "video_visual_pipeline"
        / "run.py"
    )

    with temporary_dependency_stubs():
        spec = importlib.util.spec_from_file_location(
            "thumbnail_render_contract_under_test",
            module_path,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module.create_thumbnail


class ThumbnailRenderContractTests(unittest.TestCase):
    def test_render_uses_v2_gold_layout(self):
        create_thumbnail = load_create_thumbnail()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            background = root / "background.png"
            output = root / "thumbnail.jpg"
            Image.new(
                "RGB",
                (1536, 1024),
                (8, 24, 48),
            ).save(background)

            metrics = create_thumbnail(
                background_path=background,
                output_path=output,
                overlay_text="TWO SECOND VERDICT",
                text_position="right",
            )

            self.assertTrue(output.exists())

            with Image.open(output) as image:
                self.assertEqual(image.size, (1280, 720))

            self.assertEqual(
                metrics["standard_name"],
                "hiddenova_cinematic_v2",
            )
            self.assertEqual(metrics["text_position"], "left")
            self.assertEqual(metrics["subject_position"], "right")
            self.assertEqual(metrics["highlight_line"], "VERDICT")
            self.assertEqual(metrics["line_count"], 3)
            self.assertGreaterEqual(metrics["font_size"], 112)


if __name__ == "__main__":
    unittest.main()
