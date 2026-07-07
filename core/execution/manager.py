from .context import (
    load_or_create_context,
    save_context,
    apply_image_qa_result,
    apply_image_revision_created,
)


class ExecutionManager:
    def __init__(self, channel: str, pipeline: str):
        self.channel = channel
        self.pipeline = pipeline

    def load(self):
        return load_or_create_context(
            channel=self.channel,
            pipeline=self.pipeline
        )

    def image_qa_completed(self, image_qa_data: dict):
        context = self.load()
        context = apply_image_qa_result(
            context=context,
            image_qa_data=image_qa_data
        )
        save_context(context)
        return context

    def image_revision_completed(self):
        context = self.load()
        context = apply_image_revision_created(context)
        save_context(context)
        return context