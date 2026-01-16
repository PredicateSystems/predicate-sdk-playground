"""
Simplified video generation without TextClip (no ImageMagick required)
Adds camera panning effect for the final scene
Adds token usage overlay using PIL
"""
from moviepy.editor import (
    ImageClip,
    CompositeVideoClip,
    concatenate_videoclips,
    VideoFileClip,
    clips_array
)
from moviepy.video.fx.all import resize
from PIL import Image, ImageDraw, ImageFont
import os
from typing import Dict, Any
import numpy as np


def add_token_overlay(image_path: str, token_count: int, scene_name: str) -> str:
    """
    Add token usage overlay to an image using PIL

    Args:
        image_path: Path to the original image
        token_count: Number of tokens used
        scene_name: Name of the scene

    Returns:
        Path to the new image with overlay
    """
    # Open the image
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # Try to use a nice font, fallback to default if not available
    try:
        # Try common system fonts
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    except:
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except:
            # Fallback to default font
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Get image dimensions
    width, height = img.size

    # Create semi-transparent overlay box in the center
    if token_count > 0:
        # Token text
        token_text = f"Tokens: {token_count}"

        # Calculate text size and position (center of image)
        bbox = draw.textbbox((0, 0), token_text, font=font_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Position in center of image
        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Draw semi-transparent background rectangle
        padding = 20
        bg_box = [
            x - padding,
            y - padding,
            x + text_width + padding,
            y + text_height + padding
        ]

        # Create overlay with transparency
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Draw rounded rectangle background (semi-transparent black)
        overlay_draw.rectangle(bg_box, fill=(0, 0, 0, 180))

        # Composite overlay onto original image
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        img = Image.alpha_composite(img, overlay)

        # Draw text on top
        draw = ImageDraw.Draw(img)
        draw.text((x, y), token_text, fill=(255, 215, 0, 255), font=font_large)  # Gold color

    # Convert back to RGB for video
    if img.mode == 'RGBA':
        rgb_img = Image.new('RGB', img.size, (0, 0, 0))
        rgb_img.paste(img, mask=img.split()[3])  # Use alpha channel as mask
        img = rgb_img

    # Save the modified image
    output_path = image_path.replace('.png', '_overlay.png')
    img.save(output_path)

    return output_path


def create_demo_video(screenshots_dir: str, token_summary: Dict[str, Any], output_path: str):
    """
    Create a video from screenshots with token usage overlay
    Uses image-based text overlays instead of TextClip to avoid ImageMagick dependency

    Args:
        screenshots_dir: Directory containing scene screenshots
        token_summary: Token tracking summary from TokenTracker
        output_path: Output video file path
    """
    print(f"\nCreating video from screenshots in {screenshots_dir}...")

    # Get all screenshots in order (exclude annotated and overlay versions)
    screenshot_files = sorted([
        f for f in os.listdir(screenshots_dir)
        if f.endswith('.png') and 'scene' in f.lower()
        and '_annotated' not in f and '_overlay' not in f
    ])

    if not screenshot_files:
        print(f"No screenshots found in {screenshots_dir}")
        return

    print(f"Found {len(screenshot_files)} screenshots")
    clips = []

    # Create clips for each scene
    for i, screenshot_file in enumerate(screenshot_files):
        img_path = os.path.join(screenshots_dir, screenshot_file)
        print(f"  Processing {screenshot_file}...")

        # Determine if this is the "Add to Cart" scene (last meaningful scene)
        is_add_to_cart_scene = (i == len(screenshot_files) - 2) or \
                               ('scene4' in screenshot_file.lower() or
                                'scene5' in screenshot_file.lower() or
                                'product_details' in screenshot_file.lower())

        # Get token usage for this scene
        scene_tokens = 0
        for interaction in token_summary['interactions']:
            if f"scene {i+1}" in interaction['scene'].lower():
                scene_tokens = interaction['total']
                break

        # Add token overlay to image
        if scene_tokens > 0:
            print(f"    Adding token overlay ({scene_tokens} tokens)...")
            img_path = add_token_overlay(img_path, scene_tokens, screenshot_file)

        # Use simple ImageClip to avoid PIL.ANTIALIAS compatibility issues with newer Pillow
        # Ken Burns effects are disabled due to MoviePy/Pillow incompatibility
        duration = 5.0 if is_add_to_cart_scene else 3.0
        clip = ImageClip(img_path, duration=duration)

        clips.append(clip)

    # Create summary screen at the end
    print("  Creating summary screen...")
    # Use a simple black background for summary
    # Since we can't use TextClip, we'll just show the last screenshot for now
    # In production, you'd create a summary image with PIL
    if screenshot_files:
        summary_clip = ImageClip(os.path.join(screenshots_dir, screenshot_files[-1]), duration=3.0)
        clips.append(summary_clip)

    # Concatenate all clips
    print("  Concatenating clips...")
    final_video = concatenate_videoclips(clips, method="compose")

    # Write video file
    print(f"  Writing video to {output_path}...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_video.write_videofile(
        output_path,
        fps=30,  # 30 FPS for smooth panning
        codec='libx264',
        audio=False,
        preset='medium',
        logger=None  # Suppress moviepy logs
    )

    print(f"\n✅ Video created: {output_path}")
    print(f"   Total duration: {final_video.duration:.1f}s")
    print(f"   Scenes: {len(clips)}")


def create_panning_clip(image_path: str, duration: float = 5.0, scene_tokens: int = 0):
    """
    Create a clip with camera panning effect (vertical pan to show Add to Cart button)

    The image should be taller than the video output to allow panning room.
    We'll pan from top to bottom with a smooth bezier curve motion.

    Args:
        image_path: Path to the screenshot
        duration: Duration of the clip in seconds
        scene_tokens: Token count for this scene (for display)

    Returns:
        VideoClip with panning effect
    """
    from PIL import Image

    # Load image to get dimensions
    img = Image.open(image_path)
    img_width, img_height = img.size

    # Video output dimensions (standard HD)
    video_width = 1920
    video_height = 1080

    # If image height is less than video height, no panning needed
    if img_height <= video_height:
        return ImageClip(image_path, duration=duration)

    # Calculate maximum pan distance
    max_pan = img_height - video_height

    # Create panning effect using a custom position function
    def pan_position(t):
        """
        Smooth panning using bezier curve
        t: current time (0 to duration)
        Returns: (x, y) position of the clip relative to the canvas
        """
        # Normalize time to 0-1
        progress = t / duration

        # Bezier curve for smooth acceleration/deceleration
        # Using cubic bezier: P(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
        # Control points for smooth S-curve: P0=0, P1=0.25, P2=0.75, P3=1
        eased = 3 * (1 - progress)**2 * progress * 0.25 + \
                3 * (1 - progress) * progress**2 * 0.75 + \
                progress**3

        # Calculate Y position (negative because we're moving the image up)
        y = -int(eased * max_pan)

        # X position stays centered
        x = 0

        return (x, y)

    # Create the base clip
    base_clip = ImageClip(image_path)

    # Apply the panning position function
    panned_clip = base_clip.set_position(pan_position).set_duration(duration)

    # Create a composite with fixed video dimensions
    # This crops the image to show only the video_height portion
    final_clip = CompositeVideoClip(
        [panned_clip],
        size=(video_width, video_height)
    ).set_duration(duration)

    return final_clip


def create_ken_burns_clip(image_path: str, duration: float = 3.0, zoom_direction: str = 'in', pan_direction: str = 'right'):
    """
    Create a Ken Burns effect clip (slow zoom + pan)

    Args:
        image_path: Path to the screenshot
        duration: Duration of the clip in seconds
        zoom_direction: 'in' for zoom in, 'out' for zoom out
        pan_direction: 'left', 'right', 'up', 'down'

    Returns:
        VideoClip with Ken Burns effect
    """
    from PIL import Image

    # Load image to get dimensions
    img = Image.open(image_path)
    img_width, img_height = img.size

    # Video output dimensions (standard HD)
    video_width = 1920
    video_height = 1080

    # Zoom range (start and end scale)
    if zoom_direction == 'in':
        scale_start = 1.0  # Start at normal size
        scale_end = 1.15   # End zoomed in by 15%
    else:
        scale_start = 1.15  # Start zoomed in
        scale_end = 1.0     # End at normal size

    # Pan range based on direction
    pan_amount = 50  # pixels

    # Use resize and position approach for Ken Burns effect
    base_clip = ImageClip(image_path)

    def resize_func(t):
        """Progressive resize"""
        progress = t / duration
        eased = 3 * (1 - progress)**2 * progress * 0.25 + \
                3 * (1 - progress) * progress**2 * 0.75 + \
                progress**3
        current_scale = scale_start + (scale_end - scale_start) * eased
        return current_scale

    def position_func(t):
        """Progressive position change"""
        progress = t / duration
        eased = 3 * (1 - progress)**2 * progress * 0.25 + \
                3 * (1 - progress) * progress**2 * 0.75 + \
                progress**3

        # Calculate pan offset
        if pan_direction == 'right':
            pan_x = -int(pan_amount * eased)  # Negative because image moves opposite
            pan_y = 0
        elif pan_direction == 'left':
            pan_x = int(pan_amount * eased)
            pan_y = 0
        elif pan_direction == 'down':
            pan_x = 0
            pan_y = -int(pan_amount * eased)
        elif pan_direction == 'up':
            pan_x = 0
            pan_y = int(pan_amount * eased)
        else:
            pan_x = pan_y = 0

        return (pan_x, pan_y)

    # Apply progressive resize and position
    clip = base_clip.resize(lambda t: resize_func(t))
    clip = clip.set_position(lambda t: position_func(t))
    clip = clip.set_duration(duration)

    # Composite to fixed size
    final_clip = CompositeVideoClip(
        [clip],
        size=(video_width, video_height)
    ).set_duration(duration)

    return final_clip


def create_side_by_side_comparison(demo1_video: str, demo2_video: str, output_path: str):
    """
    Create side-by-side comparison video

    Args:
        demo1_video: Path to Demo 1 video (SDK)
        demo2_video: Path to Demo 2 video (Vision)
        output_path: Output comparison video path
    """
    print(f"\nCreating side-by-side comparison video...")

    if not os.path.exists(demo1_video):
        print(f"Error: Demo 1 video not found: {demo1_video}")
        return

    if not os.path.exists(demo2_video):
        print(f"Error: Demo 2 video not found: {demo2_video}")
        return

    # Load both videos
    print("  Loading videos...")
    clip1 = VideoFileClip(demo1_video)
    clip2 = VideoFileClip(demo2_video)

    # Resize to half width for side-by-side
    print("  Resizing clips...")
    clip1_resized = clip1.resize(width=960)
    clip2_resized = clip2.resize(width=960)

    # Make them the same duration (use shorter one)
    min_duration = min(clip1.duration, clip2.duration)
    clip1_resized = clip1_resized.set_duration(min_duration)
    clip2_resized = clip2_resized.set_duration(min_duration)

    # Create side-by-side layout
    print("  Creating side-by-side layout...")
    final_clip = clips_array([[clip1_resized, clip2_resized]])

    # Write comparison video
    print(f"  Writing comparison video to {output_path}...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_clip.write_videofile(
        output_path,
        fps=30,
        codec='libx264',
        audio=False,
        preset='medium',
        logger=None
    )

    print(f"\n✅ Comparison video created: {output_path}")
