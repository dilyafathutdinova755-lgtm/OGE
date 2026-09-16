"""Renders the centered hook-text overlay (playbook section 05).

Font size is chosen as large as possible while keeping the phrase to at
most 4 lines. Text is always white; stroke width and drop-shadow strength
are derived from the brightness/noisiness of the photo directly behind the
text, so the same caption stays readable on both light and dark frames.
"""
from __future__ import annotations

import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

CANVAS_W, CANVAS_H = 1080, 1920
SIDE_MARGIN = 90
MAX_LINES = 4
MAX_FONT_SIZE = 132
MIN_FONT_SIZE = 44
LINE_SPACING = 1.18


def cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale+crop so the photo fills target_w x target_h with no empty bars."""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_text(text: str) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    max_width = CANVAS_W - 2 * SIDE_MARGIN
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -4):
        font = ImageFont.truetype(FONT_PATH, size)
        lines = _wrap_lines(text, font, max_width)
        if len(lines) <= MAX_LINES and all(font.getlength(line) <= max_width for line in lines):
            return font, lines
    # Fall back to the smallest size, hard-wrapped to MAX_LINES.
    font = ImageFont.truetype(FONT_PATH, MIN_FONT_SIZE)
    return font, _wrap_lines(text, font, max_width)[:MAX_LINES]


def _luminance_stats(photo: Image.Image, box: tuple[int, int, int, int]) -> tuple[float, float]:
    region = np.asarray(photo.convert("L").crop(box), dtype=np.float32)
    return float(region.mean()), float(region.std())


def build_overlay(photo_path: pathlib.Path, text: str) -> tuple[Image.Image, Image.Image]:
    """Returns (text_overlay_rgba, cover_cropped_photo_rgb) both CANVAS_W x CANVAS_H."""
    photo = cover_crop(Image.open(photo_path).convert("RGB"), CANVAS_W, CANVAS_H)
    font, lines = _fit_text(text)

    line_height = int(font.size * LINE_SPACING)
    block_height = line_height * len(lines)
    top = (CANVAS_H - block_height) // 2

    pad = 40
    box = (
        max(0, SIDE_MARGIN - pad),
        max(0, top - pad),
        min(CANVAS_W, CANVAS_W - SIDE_MARGIN + pad),
        min(CANVAS_H, top + block_height + pad),
    )
    mean_lum, noise = _luminance_stats(photo, box)

    stroke_width = round(2 + (mean_lum / 255) * 5)
    shadow_alpha = int(min(255, 130 + min(noise, 60) * 2))
    shadow_blur = 3 + min(noise / 20, 5)

    shadow_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    text_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)

    y = top
    for line in lines:
        line_w = font.getlength(line)
        x = (CANVAS_W - line_w) / 2
        shadow_draw.text((x, y), line, font=font, fill=(0, 0, 0, shadow_alpha))
        text_draw.text(
            (x, y), line, font=font, fill=(255, 255, 255, 255),
            stroke_width=stroke_width, stroke_fill=(0, 0, 0, 255),
        )
        y += line_height

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
    overlay = Image.alpha_composite(shadow_layer, text_layer)
    return overlay, photo
