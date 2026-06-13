from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import fitz

from sakura.content import documents as sakura_documents
from sakura.content import importer as sakura_import
from sakura.content.pdf import PreviousQuestionState, page_range, save_uploaded_pdf


def import_pdf(
    filename: str,
    pdf_bytes: bytes,
    *,
    title: str = "",
    subject: str = "",
    document_kind: str,
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

