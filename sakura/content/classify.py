from __future__ import annotations

import re
from dataclasses import dataclass

import fitz


CHAPTER_RULE_AUTO = "auto"
CHAPTER_RULE_RIGHT_HEADER = "right_header"
CHAPTER_RULE_RIGHT_HEADER_STRICT = "right_header_strict"
CHAPTER_RULE_KEYWORD_HEADER = "keyword_header"
CHAPTER_RULE_WD_TABLET_TOPBAR = "wd_tablet_topbar"
CHAPTER_RULE_NUMBERED = "numbered"
CHAPTER_RULE_NONE = "none"
CHAPTER_RULES = {
    CHAPTER_RULE_AUTO,
    CHAPTER_RULE_RIGHT_HEADER,
    CHAPTER_RULE_RIGHT_HEADER_STRICT,
    CHAPTER_RULE_KEYWORD_HEADER,
    CHAPTER_RULE_WD_TABLET_TOPBAR,
    CHAPTER_RULE_NUMBERED,
    CHAPTER_RULE_NONE,
}
CHAPTER_TITLE_KEYWORDS = (
    r"函数|极限|连续|导数|微分|积分|级数|矩阵|行列式|向量|线性方程|特征值|特征向量|二次型|"
    r"概率|随机变量|参数估计|假设检验|分布|统计|网络|数据库|操作系统|组成原理|数据结构|算法"
)


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


def resolve_import_chapter(
    *,
    page,
    text: str,
    document_kind: str,
    chapters: ChapterCarryState,
    default_chapter: str,
    mock_paper_kind: str,
    mock_paper_chapter: str,
    chapter_rule: str = CHAPTER_RULE_AUTO,
    extract_chapter=None,
) -> str:
    if document_kind == mock_paper_kind:
        return mock_paper_chapter
    chapter_rule = normalize_chapter_rule(chapter_rule)
    if chapter_rule == CHAPTER_RULE_NONE:
        return default_chapter
    extractor = extract_chapter or extract_chapter_from_page
    if extract_chapter:
        extracted = extractor(page, text, default_chapter)
    else:
        extracted = extractor(page, text, default_chapter, chapter_rule=chapter_rule)
    return chapters.resolve(extracted)


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


def normalize_chapter_rule(value: str | None) -> str:
    clean = normalize_label(value or "", CHAPTER_RULE_AUTO).lower().replace("-", "_")
    aliases = {
        "": CHAPTER_RULE_AUTO,
        "default": CHAPTER_RULE_AUTO,
        "auto_detect": CHAPTER_RULE_AUTO,
        "automatic": CHAPTER_RULE_AUTO,
        "自动识别": CHAPTER_RULE_AUTO,
        "right": CHAPTER_RULE_RIGHT_HEADER,
        "right_top": CHAPTER_RULE_RIGHT_HEADER,
        "right_header": CHAPTER_RULE_RIGHT_HEADER,
        "header_right": CHAPTER_RULE_RIGHT_HEADER,
        "右上角": CHAPTER_RULE_RIGHT_HEADER,
        "右上角小节标题": CHAPTER_RULE_RIGHT_HEADER,
        "strict_right": CHAPTER_RULE_RIGHT_HEADER_STRICT,
        "strict_right_header": CHAPTER_RULE_RIGHT_HEADER_STRICT,
        "right_header_strict": CHAPTER_RULE_RIGHT_HEADER_STRICT,
        "严格右上角": CHAPTER_RULE_RIGHT_HEADER_STRICT,
        "严格右上角页眉": CHAPTER_RULE_RIGHT_HEADER_STRICT,
        "keyword": CHAPTER_RULE_KEYWORD_HEADER,
        "keyword_header": CHAPTER_RULE_KEYWORD_HEADER,
        "topic_keyword": CHAPTER_RULE_KEYWORD_HEADER,
        "关键词标题": CHAPTER_RULE_KEYWORD_HEADER,
        "宽松关键词标题": CHAPTER_RULE_KEYWORD_HEADER,
        "wd": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "wd_tablet": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "wd_tablet_topbar": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "topbar_repeated": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "wd平板": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "wd平板页眉": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "wd平板计算机网络": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "一研题本": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "顶部蓝条页眉": CHAPTER_RULE_WD_TABLET_TOPBAR,
        "做题本集结地": CHAPTER_RULE_RIGHT_HEADER_STRICT,
        "number": CHAPTER_RULE_NUMBERED,
        "numbered": CHAPTER_RULE_NUMBERED,
        "numbered_title": CHAPTER_RULE_NUMBERED,
        "第x章": CHAPTER_RULE_NUMBERED,
        "第x章/编号标题": CHAPTER_RULE_NUMBERED,
        "none": CHAPTER_RULE_NONE,
        "off": CHAPTER_RULE_NONE,
        "disabled": CHAPTER_RULE_NONE,
        "不自动识别": CHAPTER_RULE_NONE,
    }
    return aliases.get(clean, clean if clean in CHAPTER_RULES else CHAPTER_RULE_AUTO)


def normalize_chapter(value: str, fallback: str) -> str:
    clean = normalize_label(value, fallback)
    clean = strip_chapter_noise(clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"第\s*([一二三四五六七八九十百\d]+)\s*([章节讲])", r"第\1\2", clean)
    clean = re.sub(r"chapter\s*([0-9a-zA-Z_.-]+)", r"Chapter \1", clean, flags=re.I)
    clean = dedupe_repeated_phrase(clean)
    clean = trim_numbered_chapter_title(clean)
    return clean or fallback


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


def trim_numbered_chapter_title(value: str) -> str:
    text = normalize_label(value, "")
    if not text:
        return value
    numbered_prefix = r"\d{1,3}(?:\.\d{1,2})?\s*[.、．]\s*"
    match = re.match(rf"^({numbered_prefix}[^\s，。；;|｜·•（）()【】\[\]<>《》=+\-*/^]{{1,20}})(?:\s+.+)$", text)
    if match:
        return match.group(1).strip()
    known_terms = "行列式|矩阵|向量组|线性方程组|特征值|特征向量|二次型"
    match = re.match(rf"^({numbered_prefix}(?:{known_terms}))(?:\s*.+)$", text)
    if match:
        return match.group(1).strip()
    return text


def strip_source_prefix(value: str) -> str:
    text = normalize_label(value, "")
    text = re.sub(r"^\s*(?:微信公众号|公众号|微信)\s*[:：]?\s*\S+\s*", "", text, flags=re.I)
    return text.strip()


def is_source_noise(value: str) -> bool:
    text = normalize_label(value, "")
    if not text:
        return True
    if re.search(r"(公众号|微信公众号|微信|做题本集结地|一研题本)", text, flags=re.I):
        return extract_structured_chapter(text, "") == ""
    return False


def candidate_segments(value: str) -> list[str]:
    clean = normalize_label(value, "")
    if not clean:
        return []
    segments = [clean, strip_source_prefix(clean)]
    for part in re.split(r"\s{2,}|[|｜]", clean):
        segments.append(part)
    for part in re.split(r"[·•]", clean):
        segments.append(part)
    seen = set()
    result = []
    for segment in reversed(segments):
        text = normalize_label(segment, "")
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def extract_structured_chapter(value: str, default_chapter: str) -> str:
    patterns = [
        r"(第\s*[一二三四五六七八九十百\d]+\s*[章节讲]\s*[^\n，。；;|｜·•]{0,30})",
        r"((?:Chapter|Unit|Lecture|Section)\s*[\w.-]+[^\n，。；;|｜·•]{0,35})",
        r"(\d{1,3}(?:\.\d{1,2})?\s*[.、．]\s*[^\s\n，。；;|｜·•（）()【】\[\]<>《》=+\-*/^]{1,20})",
        r"([一二三四五六七八九十]+[.、]\s*[^\s\n，。；;|｜·•（）()【】\[\]<>《》=+\-*/^]{2,20})",
    ]
    for segment in candidate_segments(value):
        for pattern in patterns:
            match = re.search(pattern, segment, flags=re.I)
            if match:
                chapter = normalize_chapter(match.group(1), default_chapter)
                if (
                    chapter
                    and chapter != default_chapter
                    and not is_source_noise(chapter)
                    and is_plausible_structured_chapter(chapter)
                ):
                    return chapter
    return default_chapter


def is_plausible_structured_chapter(value: str) -> bool:
    text = normalize_label(value, "")
    numeric = re.match(r"^(\d{1,3})(?:\.\d{1,2})?\s*[.、．]\s*(.+)$", text)
    if numeric:
        if int(numeric.group(1)) <= 0:
            return False
        title = numeric.group(2).strip()
        if re.fullmatch(r"[\d.]+", title):
            return False
        if len(title) <= 2 and not re.search(CHAPTER_TITLE_KEYWORDS, title):
            return False
        return True
    return True


def extract_chapter_from_candidate(value: str, default_chapter: str, *, allow_keyword: bool = True) -> str:
    structured = extract_structured_chapter(value, default_chapter)
    if structured != default_chapter:
        return structured
    if not allow_keyword:
        return default_chapter
    for segment in candidate_segments(value):
        if is_source_noise(segment):
            continue
        if looks_like_chapter(segment):
            chapter = normalize_chapter(segment, default_chapter)
            if chapter != default_chapter and not is_source_noise(chapter):
                return chapter
    return default_chapter


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
        rf"({CHAPTER_TITLE_KEYWORDS}|随机|线代|线性代数)",
    ]
    return any(re.search(pattern, clean, flags=re.I) for pattern in chapter_patterns)


def extract_chapter_from_text(text: str, default_chapter: str, *, allow_keyword: bool = False) -> str:
    for line in str(text or "").splitlines()[:16]:
        chapter = extract_chapter_from_candidate(line, default_chapter, allow_keyword=allow_keyword)
        if chapter != default_chapter:
            return chapter
    return extract_chapter_from_candidate(str(text or "")[:1200], default_chapter, allow_keyword=allow_keyword)


def extract_wd_tablet_topbar_chapter(value: str, default_chapter: str) -> str:
    clean = normalize_label(value, "")
    if not clean:
        return default_chapter
    clean = re.sub(r"\bWD\s*计算机[^\s]*", " ", clean, flags=re.I)
    clean = re.sub(r"\s*(?:微信公众号|公众号|微信)\s*[:：]?.*$", " ", clean, flags=re.I)
    clean = re.sub(r"\s*一研题本.*$", " ", clean, flags=re.I)
    clean = normalize_label(clean, "")
    repeated = re.match(
        r"^(?P<title>\d{1,2}(?:\.\d{1,2}){1,3}\s*[^\s，。；;|｜·•（）()【】\[\]<>《》=+\-*/^]{2,30})(?:\s+(?P=title))(?:\s+.*)?$",
        clean,
    )
    if repeated:
        return normalize_chapter(repeated.group("title"), default_chapter)
    section = re.search(
        r"(\d{1,2}(?:\.\d{1,2}){1,3}\s*[^\s，。；;|｜·•（）()【】\[\]<>《》=+\-*/^]{2,30})",
        clean,
    )
    if section:
        return normalize_chapter(section.group(1), default_chapter)
    return default_chapter


def extract_wd_tablet_topbar_from_page(page, default_chapter: str) -> str:
    width = max(page.rect.width, 1)
    height = max(page.rect.height, 1)
    candidates = []
    for block in page.get_text("blocks", sort=True):
        if len(block) < 5:
            continue
        x0, y0, x1, y1, block_text = block[:5]
        if y0 <= height * 0.06 and y1 <= height * 0.08 and (x1 - x0) >= width * 0.25:
            clean = re.sub(r"\s+", " ", str(block_text)).strip()
            if clean:
                candidates.append(clean)

    top_words = []
    for word in page.get_text("words", sort=True):
        if len(word) < 5:
            continue
        _x0, y0, _x1, y1, word_text = word[:5]
        if y0 <= height * 0.06 and y1 <= height * 0.08:
            top_words.append(str(word_text))
    joined = normalize_label(" ".join(top_words), "")
    if joined:
        candidates.append(joined)

    for candidate in candidates:
        chapter = extract_wd_tablet_topbar_chapter(candidate, default_chapter)
        if chapter != default_chapter:
            return chapter
    return default_chapter


def extract_chapter_from_page(page, text: str, default_chapter: str, *, chapter_rule: str = CHAPTER_RULE_AUTO) -> str:
    chapter_rule = normalize_chapter_rule(chapter_rule)
    if chapter_rule == CHAPTER_RULE_NONE:
        return default_chapter
    if chapter_rule == CHAPTER_RULE_WD_TABLET_TOPBAR:
        return extract_wd_tablet_topbar_from_page(page, default_chapter)
    strict_right_header = chapter_rule == CHAPTER_RULE_RIGHT_HEADER_STRICT
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
        if not strict_right_header and y1 <= height * 0.22:
            candidates.append((1, "top", clean))
        right_x_ratio = 0.45 if strict_right_header else 0.38
        right_y_ratio = 0.09 if strict_right_header else 0.35
        if x0 >= width * right_x_ratio and y1 <= height * right_y_ratio:
            candidates.append((0, "right", clean))
        if not strict_right_header and y1 <= height * 0.35 and looks_like_chapter(clean):
            candidates.append((2, "chapterish", clean))

    words = page.get_text("words", sort=True)
    top_words = []
    right_top_words = []
    for word in words:
        if len(word) < 5:
            continue
        x0, _y0, _x1, y1, word_text = word[:5]
        if not strict_right_header and y1 <= height * 0.16:
            top_words.append(str(word_text))
        right_word_x_ratio = 0.45 if strict_right_header else 0.4
        right_word_y_ratio = 0.09 if strict_right_header else 0.32
        if x0 >= width * right_word_x_ratio and y1 <= height * right_word_y_ratio:
            right_top_words.append(str(word_text))
    for joined in (" ".join(right_top_words), " ".join(top_words)):
        joined = normalize_label(joined, "")
        if joined:
            zone = "right" if joined == " ".join(right_top_words).strip() else "top"
            candidates.append((0 if zone == "right" else 1, zone, joined))

    if strict_right_header:
        candidates = [item for item in candidates if item[1] == "right"]

    allow_keyword = chapter_rule in {CHAPTER_RULE_RIGHT_HEADER, CHAPTER_RULE_RIGHT_HEADER_STRICT, CHAPTER_RULE_KEYWORD_HEADER}
    for _priority, _zone, candidate in sorted(candidates, key=lambda item: item[0]):
        candidate_allows_keyword = allow_keyword and (chapter_rule == CHAPTER_RULE_KEYWORD_HEADER or _zone in {"top", "right"})
        chapter = extract_chapter_from_candidate(candidate, default_chapter, allow_keyword=candidate_allows_keyword)
        if chapter != default_chapter:
            return chapter

    chapter = extract_chapter_from_text(
        text,
        default_chapter,
        allow_keyword=chapter_rule == CHAPTER_RULE_KEYWORD_HEADER,
    )
    if chapter != default_chapter:
        return chapter
    return default_chapter


def extract_text_and_chapters(
    pdf_path,
    document_kind: str,
    *,
    default_chapter: str,
    mock_paper_kind: str,
    mock_paper_chapter: str,
    chapter_rule: str = CHAPTER_RULE_AUTO,
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
            extracted = extract_chapter_from_page(page, text, default_chapter, chapter_rule=chapter_rule)
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
