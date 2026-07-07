import base64

from openai import OpenAI


def generate_openai_image(prompt_data: dict) -> bytes:
    client = OpenAI()

    response = client.images.generate(
        model=prompt_data["model"],
        prompt=prompt_data["prompt"],
        size=prompt_data["size"],
        quality=prompt_data["quality"],
        n=1
    )

    image_base64 = response.data[0].b64_json

    if not image_base64:
        raise ValueError("OpenAI did not return image data.")

    return base64.b64decode(image_base64)