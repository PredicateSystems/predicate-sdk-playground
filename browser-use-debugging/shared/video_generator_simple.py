"""
Simplified video generation without TextClip (no ImageMagick required).

Copied from: sentience-sdk-playground/amazon_shopping/shared/video_generator_simple.py
to keep demo visuals consistent across playground projects.

This takes per-step screenshots and optionally overlays token usage.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from moviepy.editor import ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont


def add_token_overlay(image_path: str, token_count: int, scene_name: str) -> str:
    """
    Add token usage overlay to an image using PIL.

    Args:
        image_path: Path to the original image
        token_count: Number of tokens used
        scene_name: Name of the scene (unused but kept for API compatibility)

    Returns:
        Path to the new image with overlay
    """
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # Try to use a nice font, fallback to default if not available
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
    except Exception:
        try:
            font_large = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48
            )
        except Exception:
            font_large = ImageFont.load_default()

    width, height = img.size

    if token_count > 0:
        token_text = f"Tokens: {token_count}"
        bbox = draw.textbbox((0, 0), token_text, font=font_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        padding = 20
        bg_box = [x - padding, y - padding, x + text_width + padding, y + text_height + padding]

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(bg_box, fill=(0, 0, 0, 180))

        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay)

        draw = ImageDraw.Draw(img)
        draw.text((x, y), token_text, fill=(255, 215, 0, 255), font=font_large)

    # Convert back to RGB for video
    if img.mode == "RGBA":
        rgb_img = Image.new("RGB", img.size, (0, 0, 0))
        rgb_img.paste(img, mask=img.split()[3])
        img = rgb_img

    output_path = image_path.replace(".png", "_overlay.png")
    img.save(output_path)
    return output_path


def create_demo_video(screenshots_dir: str, token_summary: Dict[str, Any], output_path: str):
    """
    Create a video from screenshots with token usage overlay (if present).

    Screenshots should include "scene" in the filename to be picked up.
    """
    print(f"\nCreating video from screenshots in {screenshots_dir}...")

    screenshot_files = sorted(
        [
            f
            for f in os.listdir(screenshots_dir)
            if f.endswith(".png")
            and "scene" in f.lower()
            and "_annotated" not in f
            and "_overlay" not in f
        ]
    )

    if not screenshot_files:
        print(f"No screenshots found in {screenshots_dir}")
        return

    print(f"Found {len(screenshot_files)} screenshots")
    clips = []

    for i, screenshot_file in enumerate(screenshot_files):
        img_path = os.path.join(screenshots_dir, screenshot_file)

        # Match token usage for "Scene {i+1}" if present
        scene_tokens = 0
        for interaction in token_summary.get("interactions", []):
            if f"scene {i+1}" in (interaction.get("scene", "").lower()):
                scene_tokens = int(interaction.get("total", 0) or 0)
                break

        if scene_tokens > 0:
            img_path = add_token_overlay(img_path, scene_tokens, screenshot_file)

        duration = 3.0
        clips.append(ImageClip(img_path, duration=duration))

    final_video = concatenate_videoclips(clips, method="compose")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_video.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio=False,
        preset="medium",
        logger=None,
    )
    print(f"\n✅ Video created: {output_path}")

