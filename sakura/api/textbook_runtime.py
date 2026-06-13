from __future__ import annotations

from pathlib import Path
from typing import Callable

from sakura.content import textbook as sakura_textbook


def import_textbook_pdf(
    filename: str,
    pdf_bytes: bytes,
    *,
    title: str = "",
    subject: str = "",
    upload_dir: Path,
    connect: Callable,
    normalize_label: Callable[[str, str], str],
    default_subject: str,
) -> dict:
    return sakura_textbook.import_textbook_pdf(
        filename,
        pdf_bytes,
        title=title,
        subject=subject,
        upload_dir=upload_dir,
        connect=connect,
        normalize_label=normalize_label,
        default_subject=default_subject,
    )


def build_textbook_context(
    conn,
    textbook_id: str,
    page_number: int,
    paragraph_index: int = 0,
    *,
    to_public_path: Callable[[str], str],
    page_dir: Path,
    render_page_image: Callable,
    ocr_image_text: Callable[[str], str] | None = None,
    full_page_ocr: bool = True,
) -> tuple[dict, dict]:
    return sakura_textbook.build_textbook_context(
        conn,
        textbook_id,
        page_number,
        paragraph_index,
        to_public_path=to_public_path,
        page_dir=page_dir,
        render_page_image=render_page_image,
        ocr_image_text=ocr_image_text,
        full_page_ocr=full_page_ocr,
    )


def explain_textbook_with_ai(
    book: dict,
    page: dict,
    message: str,
    history: list[dict],
    *,
    llm_enabled: bool,
    call_llm_messages: Callable,
    vision_enabled: bool = False,
    call_llm_vision: Callable | None = None,
    image_to_data_url: Callable[[str], str] | None = None,
) -> str:
    return sakura_textbook.explain_textbook(
        book,
        page,
        message,
        history,
        llm_enabled=llm_enabled,
        call_llm_messages=call_llm_messages,
        vision_enabled=vision_enabled,
        call_llm_vision=call_llm_vision,
        image_to_data_url=image_to_data_url,
    )


def explain_textbook_page_with_vision(
    book: dict,
    page: dict,
    message: str = "",
    *,
    vision_enabled: bool,
    call_llm_vision: Callable,
    image_to_data_url: Callable[[str], str],
) -> str:
    if not vision_enabled:
        return (
            "当前没有配置视觉模型。请在 AI 设置里填写支持图片输入的视觉模型名；"
            "视觉 Key / Base URL 可单独填写，也可以留空复用上面的文本模型配置。"
        )
    data_url = image_to_data_url(page.get("image_path", ""))
    if not data_url:
        return "当前页图片没有读到，无法交给视觉模型。请先读取/扫描当前页，或重新导入教材。"
    page_text = (page.get("page_text") or "").strip()
    prompt = message.strip() or "请直接阅读这页教材截图，概括本页知识点，解释图表/公式，并指出容易误解的地方。"
    messages = [
        {
            "role": "system",
            "content": (
                "你是 Sakura 做题集的教材精读老师。请根据用户提供的当前页截图回答，"
                "重点识别图片中的正文、公式、图表、箭头和版式关系。不要编造图片外的内容。"
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"教材：{book.get('title')} / {book.get('subject')}\n"
                        f"页码：{page.get('display_page') or page.get('page_number')}\n"
                        f"OCR/文本层参考：{page_text[:1800] or '本页没有可用文字参考，请以图片为准。'}\n\n"
                        f"任务：{prompt}"
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    return call_llm_vision(messages, temperature=0.25)

