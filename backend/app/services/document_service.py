import os
import uuid
from pathlib import Path

import PyPDF2
from docx import Document as DocxDocument
from docx.document import Document as _DocxDocumentClass
from docx.table import Table as _DocxTable
from docx.text.paragraph import Paragraph as _DocxParagraph

from app.config import settings


def extract_text(file_path: str, content_type: str) -> str:
    """Extract text from PDF, DOCX, or TXT files."""
    if content_type == "application/pdf" or file_path.endswith(".pdf"):
        return _extract_pdf(file_path)
    elif content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ) or file_path.endswith(".docx"):
        return _extract_docx(file_path)
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


def _extract_pdf(file_path: str) -> str:
    text_parts = []
    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _iter_block_items(parent):
    """Yield paragraphs and tables from a docx body in document order.

    python-docx exposes paragraphs and tables in separate collections that do
    not preserve their relative order. Walking the underlying XML body lets us
    reconstruct the original sequence so table content (e.g. procedure steps)
    is not dropped.
    """
    if isinstance(parent, _DocxDocumentClass):
        parent_elm = parent.element.body
    else:
        parent_elm = parent._element

    for child in parent_elm.iterchildren():
        if child.tag.endswith("}p"):
            yield _DocxParagraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield _DocxTable(child, parent)


def _dedupe_cell_text(raw: str) -> str:
    """Collapse repeated lines within a cell (vertical-merge artifact).

    python-docx returns a vertically merged cell's text once per row it spans,
    e.g. "PANEL ENGINEER\nPANEL ENGINEER". Keep consecutive unique lines only,
    then flatten internal whitespace.
    """
    seen_lines = []
    prev = None
    for line in raw.splitlines():
        cleaned = " ".join(line.split())
        if not cleaned or cleaned == prev:
            continue
        seen_lines.append(cleaned)
        prev = cleaned
    return " ".join(seen_lines)


def _render_table(table: _DocxTable) -> str:
    """Render a docx table as pipe-delimited rows the LLM can read.

    Collapses duplicate cell values from merged cells (column spans) and
    repeated lines within a cell (row spans).
    """
    rows = []
    for row in table.rows:
        cells = []
        prev = None
        for cell in row.cells:
            text = _dedupe_cell_text(cell.text)
            if text and text == prev:
                continue
            cells.append(text)
            prev = text
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_docx(file_path: str) -> str:
    doc = DocxDocument(file_path)
    parts = []
    for block in _iter_block_items(doc):
        if isinstance(block, _DocxParagraph):
            if block.text.strip():
                parts.append(block.text.strip())
        elif isinstance(block, _DocxTable):
            rendered = _render_table(block)
            if rendered.strip():
                parts.append(rendered)
    return "\n\n".join(parts)


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


def save_upload(file_bytes: bytes, filename: str) -> str:
    """Save uploaded file to disk, return path."""
    ext = Path(filename).suffix
    unique_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path
