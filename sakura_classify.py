from __future__ import annotations

import re
from dataclasses import dataclass

import fitz


@dataclass
class ChapterCarryState:
    default_chapter: str
    last_chapter: str | None = None

    def resolve(self, extracted: str) -> str:
        if self.last_chapter is None:
            self.last_chapter = self.default_chapter
        if extracted != self.default_chapter:
            self.last_chapter = extracted
        chapter = self.last_chapter if self.last_chapter != self.default_chapter else extracted
        return normalize_chapter(chapter, self.default_chapter)


def classify_by_rules(text: str, keyword_rules: list[tuple[str, list[str]]], default_category: str) -> tuple[str, str, str]:
    haystack = text.lower()
    for category, keywords in keyword_rules:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category, "规则分类", "中等"
    return default_category, "待人工确认", "中等"


def normalize_label(value: str, fallback: str) -> str:
    clean = re.sub(r"\s+", " ", (value or "").strip())
    clean = re.sub(r"^[\-\s|·•]+|[\-\s|·•]+$", "", clean)
    return clean[:80] if clean else fallback


def normalize_chapter(value: str, fallback: str) -> str:
    clean = normalize_label(value, fallback)
    clean = strip_chapter_noise(clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"第\s*([一二三四五六七八九十百\d]+)\s*([章节讲])", r"第\1\2", clean)
    clean = re.sub(r"chapter\s*([0-9a-zA-Z_.-]+)", r"Chapter \1", clean, flags=re.I)
    clean = dedupe_repeated_phrase(clean)
    return clean


def strip_chapter_noise(value: str) -> str:
    text = normalize_label(value, "")
    noise_patterns = [
        r"\s*基础篇.*$",
        r"\s*强化篇.*$",
        r"\s*提高篇.*$",
        r"\s*冲刺篇.*$",
        r"\s*专项篇.*$",
        r"\s*微信公众号.*$",
        r"\s*公众号.*$",
        r"\s*微信.*$",
        r"\s*一研题本.*$",
        r"\s*考研.*$",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    return text.strip()


def dedupe_repeated_phrase(value: str) -> str:
    text = normalize_label(value, "")
    if not text:
        return value
    repeated_prefix = re.match(r"^(.{2,45}?)(?:\s+\1)(?:\s+.*)?$", text)
    if repeated_prefix:
        return repeated_prefix.group(1)
    numbered = re.match(r"^((?:第\s*)?[一二三四五六七八九十百\d]+[.、章节讲]\s*[^，。；;\s]{2,30})(?:\s+\1)(?:\s+.*)?$", text)
    if numbered:
        return numbered.group(1)
    length = len(text)
    if length % 2 == 0:
        half = length // 2
        if text[:half] == text[half:]:
            return text[:half]
    compact = re.sub(r"\s+", "", text)
    for size in range(2, len(compact) // 2 + 1):
        if len(compact) % size == 0:
            unit = compact[:size]
            if unit * (len(compact) // size) == compact:
                return unit
    match = re.match(r"^(.{2,40}?)(?:\s*\1)+$", text)
    if match:
        return match.group(1)
    return text


def looks_like_chapter(text: str) -> bool:
    clean = normalize_label(text, "")
    if not clean or len(clean) > 90:
        return False
    if re.fullmatch(r"\d+|第\s*\d+\s*页|page\s*\d+", clean, flags=re.I):
        return False
    chapter_patterns = [
        r"第\s*[一二三四五六七八九十百\d]+\s*[章节讲]",
        r"(chapter|unit|lecture|section)\s*[0-9a-zA-Z_.-]+",
        r"^[一二三四五六七八九十\d]+[.、]\s*[^，。；;]{2,}",
        r"(函数|极限|积分|微分|级数|矩阵|行列式|概率|随机|网络|数据库|操作系统|组成原理|数据结构|算法)",
    ]
    return any(re.search(pattern, clean, flags=re.I) for pattern in chapter_patterns)


def extract_chapter_from_page(page, text: str, default_chapter: str) -> str:
    candidates = []
    width = max(page.rect.width, 1)
    height = max(page.rect.height, 1)
    for block in page.get_text("blocks", sort=True):
        if len(block) < 5:
            continue
        x0, y0, _x1, y1, block_text = block[:5]
        clean = re.sub(r"\s+", " ", str(block_text)).strip()
        if not clean:
            continue
        if y1 <= height * 0.22:
            candidates.append((0, clean))
        if x0 >= width * 0.38 and y1 <= height * 0.35:
            candidates.append((1, clean))
        if y1 <= height * 0.35 and looks_like_chapter(clean):
            candidates.append((2, clean))

    words = page.get_text("words", sort=True)
    top_words = []
    right_top_words = []
    for word in words:
        if len(word) < 5:
            continue
        x0, _y0, _x1, y1, word_text = word[:5]
        if y1 <= height * 0.16:
            top_words.append(str(word_text))
        if x0 >= width * 0.4 and y1 <= height * 0.32:
            right_top_words.append(str(word_text))
    for joined in (" ".join(right_top_words), " ".join(top_words)):
        joined = normalize_label(joined, "")
        if joined:
            candidates.append((3, joined))

    for _priority, candidate in sorted(candidates, key=lambda item: item[0]):
        parts = re.split(r"\s{2,}|[|｜]", candidate)
        for part in parts:
            if looks_like_chapter(part):
                return normalize_chapter(part, default_chapter)

    patterns = [
        r"(第[一二三四五六七八九十百\d]+[章节讲][^\n，。；;]{0,30})",
        r"((?:Chapter|Unit|Lecture|Section)\s*[\w.-]+[^\n]{0,35})",
        r"([一二三四五六七八九十\d]+[.、]\s*[^\n，。；;]{2,35})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return normalize_chapter(match.group(1), default_chapter)
    return default_chapter


def extract_text_and_chapters(
    pdf_path,
    document_kind: str,
    *,
    default_chapter: str,
    mock_paper_kind: str,
    mock_paper_chapter: str,
) -> list[dict]:
    """Extract page text and chapter hints from a PDF without importing questions."""
    pages = []
    chapters = ChapterCarryState(default_chapter)
    pdf = fitz.open(pdf_path)
    try:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text", sort=True).strip()
            if document_kind == mock_paper_kind:
                pages.append({"page_number": index, "text": text, "chapter": mock_paper_chapter})
                continue
            extracted = extract_chapter_from_page(page, text, default_chapter)
            pages.append({"page_number": index, "text": text, "chapter": chapters.resolve(extracted)})
    finally:
        pdf.close()
    return pages


def classify_question_locally(
    text: str,
    *,
    subject_hint: str,
    chapter_hint: str,
    document_kind: str,
    keyword_rules: list[tuple[str, list[str]]],
    default_subject: str,
    default_category: str,
    default_chapter: str,
    default_document_kind: str,
    mock_paper_kind: str,
) -> dict:
    category, subcategory, difficulty = classify_by_rules(text, keyword_rules, default_category)
    chapter = normalize_chapter(chapter_hint, default_chapter)
    if document_kind != mock_paper_kind and category == default_category and chapter != default_chapter:
        category = chapter
        subcategory = "章节归类"
    return {
        "subject": normalize_label(subject_hint, default_subject),
        "chapter": chapter,
        "category": category,
        "subcategory": subcategory,
        "difficulty": difficulty,
        "reason": "导入阶段使用本地规则分类，不调用 DeepSeek。",
    }
