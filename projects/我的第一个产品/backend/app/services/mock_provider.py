from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


class MockProvider:
    name = "mock"

    def generate(self, output_path: Path, width: int, height: int, label: str, prompt: str | None = None) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (width, height), (238, 244, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width, max(8, height // 18)), fill=(75, 110, 190))
        draw.text((24, 30), f"图个乐 · {label}", fill=(32, 45, 80))
        draw.text((24, min(height - 40, 90)), "MOCK PREVIEW", fill=(90, 105, 130))
        image.save(output_path, format="PNG")
