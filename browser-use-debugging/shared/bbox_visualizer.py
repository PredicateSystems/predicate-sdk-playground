"""
Bounding box visualizer for Sentience snapshot elements.

Copied from: sentience-sdk-playground/amazon_shopping/shared/bbox_visualizer.py
to keep demo visuals consistent across playground projects.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFont


def visualize_api_elements(
    screenshot_path: str, snapshot_data: Dict[str, Any], output_path: str | None = None
) -> str:
    """
    Draw bounding boxes on screenshot for all snapshot elements.

    Args:
        screenshot_path: Path to the original screenshot
        snapshot_data: The snapshot data (contains 'elements' array)
        output_path: Optional output path. If None, will add '_annotated' suffix

    Returns:
        Path to the annotated image
    """
    img = Image.open(screenshot_path)
    draw = ImageDraw.Draw(img, "RGBA")

    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "C:\\Windows\\Fonts\\arial.ttf",  # Windows
    ]

    font_small = None
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_small = ImageFont.truetype(font_path, 11)
                break
            except Exception:
                pass
    if font_small is None:
        font_small = ImageFont.load_default()

    elements = snapshot_data.get("elements", [])

    for element in elements:
        bbox = element.get("bbox", {}) or {}
        x = bbox.get("x", 0)
        y = bbox.get("y", 0)
        width = bbox.get("width", 0)
        height = bbox.get("height", 0)

        visual_cues = element.get("visual_cues", {}) or {}
        is_primary = bool(visual_cues.get("is_primary", False))
        is_clickable = bool(visual_cues.get("is_clickable", False))

        if is_primary:
            border_color = (255, 215, 0, 255)  # Gold
            border_width = 4
            fill_color = (255, 215, 0, 40)
        elif is_clickable:
            border_color = (0, 255, 0, 255)  # Green
            border_width = 2
            fill_color = (0, 255, 0, 20)
        else:
            border_color = (100, 150, 255, 200)  # Blue
            border_width = 1
            fill_color = (100, 150, 255, 15)

        draw.rectangle([(x, y), (x + width, y + height)], fill=fill_color, outline=None)
        draw.rectangle(
            [(x, y), (x + width, y + height)], outline=border_color, width=border_width
        )

        text = (element.get("text", "") or "").strip()
        role = (element.get("role", "") or "").strip()
        if len(text) > 30:
            text = text[:27] + "..."

        if text and role:
            label = f"{role}: {text}"
        elif text:
            label = text
        elif role:
            label = role
        else:
            label = f"id:{element.get('id', '?')}"

        label_padding = 2
        try:
            text_bbox = draw.textbbox((0, 0), label, font=font_small)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        except Exception:
            text_width = len(label) * 7
            text_height = 12

        if y > text_height + 10:
            label_y = y - text_height - 4
        else:
            label_y = y + height + 2

        label_x = max(0, min(x, img.width - text_width - label_padding * 2))

        draw.rectangle(
            [
                (label_x, label_y),
                (
                    label_x + text_width + label_padding * 2,
                    label_y + text_height + label_padding * 2,
                ),
            ],
            fill=(0, 0, 0, 180),
        )
        text_color = (255, 215, 0, 255) if is_primary else (255, 255, 255, 255)
        draw.text(
            (label_x + label_padding, label_y + label_padding),
            label,
            fill=text_color,
            font=font_small,
        )

    if output_path is None:
        base, ext = os.path.splitext(screenshot_path)
        output_path = f"{base}_annotated{ext}"

    img.save(output_path)
    print(f"  Saved annotated screenshot: {output_path}")
    return output_path

