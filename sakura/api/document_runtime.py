from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import fitz

from sakura.content import classify as sakura_classify
from sakura.content import documents as sakura_documents
from sakura.content import importer as sakura_import
from sakura.content.pdf import PreviousQuestionState, page_range, save_uploaded_pdf


@dataclass(frozen=True)
class ImportPdfRequest:
    title: str
    subject: str
    document_kind: str
    chapter_rule: str
    start_page: int | None
    end_page: int | None
    split_questions: bool


@dataclass(frozen=True)
class DocumentUpdateRequest:
    title: str
    subject: str
    document_kind: str
    chapter_rule: str


def import_request_from_form(
    form: Any,
    *,
    default_document_kind: str,
    default_chapter_rule: str,
    positive_int: Callable[[Any, int | None], int | None],
    bool_flag: Callable[[Any], bool],
) -> ImportPdfRequest:
    return ImportPdfRequest(
        title=form.getfirst("title", ""),
        subject=form.getfirst("subject", ""),
        document_kind=form.getfirst("document_kind", default_document_kind),
        chapter_rule=form.getfirst("chapter_rule", default_chapter_rule),
        start_page=positive_int(form.getfirst("start_page", ""), None),
        end_page=positive_int(form.getfirst("end_page", ""), None),
        split_questions=bool_flag(form.getfirst("split_questions", "")),
    )


def document_update_from_payload(
    payload: dict[str, Any],
    *,
    default_subject: str,
    default_chapter_rule: str,
    mock_paper_kind: str,
    normalize_document_kind: Callable[[str | None], str],
    normalize_chapter_rule: Callable[[str | None], str],
) -> DocumentUpdateRequest:
    title = str(payload.get("title", "")).strip()
    subject = str(payload.get("subject", "")).strip() or default_subject
    document_kind = normalize_document_kind(payload.get("document_kind"))
    chapter_rule = normalize_chapter_rule(payload.get("chapter_rule"))
    if document_kind == mock_paper_kind:
        chapter_rule = default_chapter_rule
    if not title:
        raise ValueError("做题本名称不能为空。")
    if len(title) > 120:
        raise ValueError("做题本名称不能超过 120 个字符。")
    if len(subject) > 60:
        raise ValueError("科目名称不能超过 60 个字符。")
    return DocumentUpdateRequest(
        title=title,
        subject=subject,
        document_kind=document_kind,
        chapter_rule=chapter_rule,
    )


def import_pdf(
    filename: str,
    pdf_bytes: bytes,
    *,
    title: str = "",
    subject: str = "",
    document_kind: str,
    chapter_rule: str = sakura_classify.CHAPTER_RULE_AUTO,
    start_page: int | None = None,
    end_page: int | None = None,
    split_questions: bool = False,
    upload_dir: Path,
    page_dir: Path,
    connect: Callable,
    normalize_label: Callable[[str, str], str],
    normalize_document_kind: Callable[[str | None], str],
    classify_question: Callable[[str, str, str, str], dict],
    new_chapter_state: Callable,
    default_subject: str,
    default_chapter: str,
    mock_paper_kind: str,
    mock_paper_chapter: str,
) -> dict:
    doc_id = uuid.uuid4().hex
    pdf_path = save_uploaded_pdf(upload_dir, doc_id, filename, pdf_bytes)
    metadata = sakura_documents.import_metadata(
        filename=filename,
        title=title,
        subject=subject,
        document_kind=document_kind,
        normalize_label=normalize_label,
        normalize_document_kind=normalize_document_kind,
        default_subject=default_subject,
    )
    title = metadata["title"]
    subject = metadata["subject"]
    document_kind = metadata["document_kind"]
    chapter_rule = sakura_classify.normalize_chapter_rule(chapter_rule)

    now = datetime.now().isoformat(timespec="seconds")
    inserted = []
    pdf = fitz.open(pdf_path)
    chapters = new_chapter_state()
    try:
        with connect() as conn:
            sakura_documents.insert_document(
                conn,
                doc_id=doc_id,
                title=title,
                subject=subject,
                document_kind=document_kind,
                filename=filename,
                stored_path=pdf_path,
                page_count=pdf.page_count,
                chapter_rule=chapter_rule,
                created_at=now,
            )
            page_start, page_end = page_range(pdf.page_count, start_page, end_page)
            seq_no = 0
            previous_question = PreviousQuestionState()
            for index in range(page_start, page_end + 1):
                page = pdf[index - 1]
                seq_no, page_inserted = sakura_import.process_import_page(
                    conn,
                    page=page,
                    page_dir=page_dir,
                    doc_id=doc_id,
                    page_number=index,
                    seq_no=seq_no,
                    subject=subject,
                    document_kind=document_kind,
                    split_questions=split_questions,
                    chapters=chapters,
                    previous_question=previous_question,
                    created_at=now,
                    default_chapter=default_chapter,
                    mock_paper_kind=mock_paper_kind,
                    mock_paper_chapter=mock_paper_chapter,
                    chapter_rule=chapter_rule,
                    classify_question=classify_question,
                )
                inserted.extend(page_inserted)
    finally:
        pdf.close()

    return sakura_documents.imported_document_payload(
        doc_id=doc_id,
        title=title,
        subject=subject,
        document_kind=document_kind,
        filename=filename,
        questions=inserted,
    )

