from __future__ import annotations

import uuid
from pathlib import Path

from sakura.content import classify as sakura_classify
from sakura.content import pdf as sakura_pdf
from sakura.content import questions as sakura_questions


def process_question_slice(
    conn,
    *,
    page,
    page_dir: Path,
    doc_id: str,
    page_number: int,
    slice_index: int,
    seq_no: int,
    item: dict,
    page_text: str,
    subject: str,
    chapter_hint: str,
    document_kind: str,
    created_at: str,
    previous_question: sakura_pdf.PreviousQuestionState,
    classify_question,
    question_id_factory=None,
) -> dict:
    q_id = (question_id_factory or (lambda: uuid.uuid4().hex))()
    image_path, slice_text = sakura_pdf.render_question_slice(
        page,
        page_dir=page_dir,
        doc_id=doc_id,
        page_number=page_number,
        slice_index=slice_index,
        item=item,
        page_text=page_text,
    )
    summary = sakura_questions.classify_and_insert_imported_question(
        conn,
        classify_question=classify_question,
        q_id=q_id,
        doc_id=doc_id,
        page_number=page_number,
        seq_no=seq_no,
        item=item,
        image_path=image_path,
        slice_text=slice_text,
        page_text=page_text,
        subject=subject,
        chapter_hint=chapter_hint,
        document_kind=document_kind,
        created_at=created_at,
    )
    previous_question.update(q_id, image_path, item)
    return summary


def process_import_page(
    conn,
    *,
    page,
    page_dir: Path,
    doc_id: str,
    page_number: int,
    seq_no: int,
    subject: str,
    document_kind: str,
    split_questions: bool,
    chapters: sakura_classify.ChapterCarryState,
    previous_question: sakura_pdf.PreviousQuestionState,
    created_at: str,
    default_chapter: str,
    mock_paper_kind: str,
    mock_paper_chapter: str,
    classify_question,
) -> tuple[int, list[dict]]:
    page_text, starts, slices = sakura_pdf.prepare_import_page(
        page,
        document_kind=document_kind,
        split_questions=split_questions,
        mock_paper_kind=mock_paper_kind,
    )
    chapter_hint = sakura_classify.resolve_import_chapter(
        page=page,
        text=page_text,
        document_kind=document_kind,
        chapters=chapters,
        default_chapter=default_chapter,
        mock_paper_kind=mock_paper_kind,
        mock_paper_chapter=mock_paper_chapter,
    )
    continuation_text = sakura_pdf.append_import_continuation(page, starts, previous_question)
    if continuation_text:
        sakura_questions.append_question_ocr_text(conn, previous_question.question_id, continuation_text)

    inserted = []
    for slice_index, item in enumerate(slices, start=1):
        seq_no += 1
        inserted.append(
            process_question_slice(
                conn,
                page=page,
                page_dir=page_dir,
                doc_id=doc_id,
                page_number=page_number,
                slice_index=slice_index,
                seq_no=seq_no,
                item=item,
                page_text=page_text,
                subject=subject,
                chapter_hint=chapter_hint,
                document_kind=document_kind,
                created_at=created_at,
                previous_question=previous_question,
                classify_question=classify_question,
            )
        )
    return seq_no, inserted
