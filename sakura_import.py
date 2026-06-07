from __future__ import annotations

import uuid
from pathlib import Path

import sakura_pdf
import sakura_questions


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
