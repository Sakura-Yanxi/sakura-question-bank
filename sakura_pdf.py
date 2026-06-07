from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class PreviousQuestionState:
    question_id: str = ""
    image_path: Path | None = None
    value: int | None = None

    def update(self, question_id: str, image_path: Path, item: dict) -> None:
        self.question_id = question_id
        self.image_path = image_path
        value = item.get("question_value")
        self.value = int(value) if value is not None else None


def safe_pdf_filename(filename: str, fallback: str = "questions.pdf") -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or fallback


def page_range(page_count: int, start_page: int | None = None, end_page: int | None = None) -> tuple[int, int]:
    page_start = max(start_page or 1, 1)
    page_end = min(end_page or page_count, page_count)
    if page_start > page_end:
        raise ValueError("页码范围无效，请检查起止页。")
    return page_start, page_end


def render_page_image(page: fitz.Page, image_path: Path) -> None:
    page_rect = page.rect
    target_width = 1800
    zoom = max(1.4, min(3.0, target_width / max(page_rect.width, 1)))
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False, annots=True)
    pix.save(image_path)


def render_page_clip_image(page: fitz.Page, clip: fitz.Rect, image_path: Path) -> None:
    target_width = 1800
    zoom = max(1.8, min(3.5, target_width / max(clip.width, 1)))
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False, annots=True, clip=clip)
    pix.save(image_path)


def detect_question_starts(page: fitz.Page) -> list[dict]:
    """Find reliable question-number starts on one exam page."""
    page_rect = page.rect
    data = page.get_text("dict", sort=True)
    starts = []
    question_no_pattern = re.compile(r"^\s*(?:第\s*)?(\d{1,3})\s*(?:[、.．)]|题)")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            match = question_no_pattern.match(line_text)
            if not match:
                continue
            bbox = fitz.Rect(line.get("bbox", block.get("bbox", page_rect)))
            if bbox.y0 < page_rect.height * 0.015 or bbox.x0 > page_rect.width * 0.28:
                continue
            starts.append({"number": match.group(1), "value": int(match.group(1)), "y": max(page_rect.y0, bbox.y0 - 8)})

    deduped = []
    for item in sorted(starts, key=lambda item: item["y"]):
        if deduped and abs(item["y"] - deduped[-1]["y"]) < 12:
            continue
        if deduped and item["value"] <= deduped[-1]["value"]:
            continue
        deduped.append(item)
    return deduped


def detect_question_slices(page: fitz.Page, starts: list[dict] | None = None) -> list[dict]:
    """Split a multi-question exam page by visible question numbers such as 1、2. 3．"""
    page_rect = page.rect
    deduped = starts if starts is not None else detect_question_starts(page)
    if not deduped:
        return []

    slices = []
    for index, start in enumerate(deduped):
        next_y = deduped[index + 1]["y"] if index + 1 < len(deduped) else page_rect.y1 - 16
        top = max(page_rect.y0, start["y"])
        bottom = min(page_rect.y1, next_y - 4)
        if bottom - top < 36:
            continue
        clip = fitz.Rect(page_rect.x0 + 18, top, page_rect.x1 - 18, bottom)
        slices.append({"question_no": start["number"], "question_value": start["value"], "clip": clip})
    return slices


def continuation_clip_for_starts(page: fitz.Page, starts: list[dict], previous_question_value: int | None) -> fitz.Rect | None:
    """Return the top-page continuation clip when the next question starts mid-page."""
    if not starts or previous_question_value is None:
        return None
    first_start = starts[0]
    if first_start["value"] != previous_question_value + 1:
        return None
    if first_start["y"] <= page.rect.height * 0.12:
        return None
    clip = fitz.Rect(
        page.rect.x0 + 18,
        page.rect.y0 + 16,
        page.rect.x1 - 18,
        first_start["y"] - 4,
    )
    return clip if clip.height > 36 else None


def render_question_slice(page: fitz.Page, *, page_dir: Path, doc_id: str, page_number: int, slice_index: int, item: dict, page_text: str) -> tuple[Path, str]:
    """Render one imported question slice and return its image path plus extracted text."""
    clip = item.get("clip")
    if clip:
        image_path = page_dir / f"{doc_id}_page_{page_number:03d}_q{slice_index:02d}.png"
        render_page_clip_image(page, clip, image_path)
        question_text = page.get_text("text", sort=True, clip=clip).strip()
    else:
        image_path = page_dir / f"{doc_id}_page_{page_number:03d}.png"
        render_page_image(page, image_path)
        question_text = page_text
    return image_path, question_text


def trim_vertical_whitespace(image, trim_top: bool, trim_bottom: bool):
    rgb = image.convert("RGB")
    sample_width = min(360, rgb.width)
    gray = rgb.convert("L").resize((sample_width, rgb.height))
    pixels = gray.load()
    content_rows = []
    for y in range(gray.height):
        dark_pixels = sum(1 for x in range(sample_width) if pixels[x, y] < 210)
        if dark_pixels >= max(2, int(sample_width * 0.002)):
            content_rows.append(y)
    if not content_rows:
        return rgb
    padding = 24
    top = max(0, content_rows[0] - padding) if trim_top else 0
    bottom = min(rgb.height, content_rows[-1] + padding + 1) if trim_bottom else rgb.height
    return rgb.crop((0, top, rgb.width, bottom))


def append_page_clip_to_question_image(page: fitz.Page, clip: fitz.Rect, image_path: Path) -> None:
    """Append a continuation from the next PDF page below an existing question image."""
    from PIL import Image

    temp_path = image_path.parent / f".continuation_{uuid.uuid4().hex}.png"
    render_page_clip_image(page, clip, temp_path)
    try:
        with Image.open(image_path) as first_source, Image.open(temp_path) as continuation_source:
            first = trim_vertical_whitespace(first_source, trim_top=False, trim_bottom=True)
            continuation = trim_vertical_whitespace(continuation_source, trim_top=True, trim_bottom=False)
            width = max(first.width, continuation.width)
            combined = Image.new("RGB", (width, first.height + continuation.height), "white")
            combined.paste(first, (0, 0))
            combined.paste(continuation, (0, first.height))
            combined.save(image_path, format="PNG", optimize=True)
    finally:
        temp_path.unlink(missing_ok=True)


def crop_image_by_ratio(image_path: Path, crop: dict) -> None:
    """Crop an existing rendered question image with browser-provided ratio coordinates."""
    from PIL import Image

    with Image.open(image_path) as image:
        width, height = image.size
        left = max(0, min(width - 1, int(float(crop.get("x", 0)) * width)))
        top = max(0, min(height - 1, int(float(crop.get("y", 0)) * height)))
        right = max(left + 1, min(width, int(float(crop.get("w", 1)) * width) + left))
        bottom = max(top + 1, min(height, int(float(crop.get("h", 1)) * height) + top))
        cropped = image.crop((left, top, right, bottom))
        cropped.save(image_path)
