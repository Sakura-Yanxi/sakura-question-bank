from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _rapidocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def image_ocr_text(image_path: str | Path, *, min_score: float = 0.45) -> str:
    """Extract readable text from a rendered page image with RapidOCR if available."""
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return ""
    try:
        result, _elapsed = _rapidocr_engine()(str(path))
    except Exception:
        return ""
    lines: list[str] = []
    for item in result or []:
        if len(item) < 3:
            continue
        _box, text, score = item
        text = str(text or "").strip()
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            score_value = 0.0
        if text and score_value >= min_score:
            lines.append(text)
    return "\n".join(lines)
