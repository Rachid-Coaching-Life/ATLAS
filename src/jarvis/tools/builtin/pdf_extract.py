"""Bounded, read-only text extraction from a locally authorised PDF.

This module is deliberately independent of speech, the model and TaskManager.
It never executes document content or writes to the source PDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import stat


MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 20
MAX_CHARS = 30000


@dataclass(frozen=True)
class ExtractedPDF:
    pages: tuple[tuple[int, str], ...]
    total_pages: int
    truncated: bool


def extract_pdf_text(path: Path, allowed_root: Path, *, max_pages: int = MAX_PAGES) -> ExtractedPDF:
    """Extract bounded per-page text; reject files outside allowed_root.

    Caller supplies a permitted directory, not an arbitrary full-disk search.
    Scanned/image-only PDF pages return empty text; no OCR is attempted.
    """
    if not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("Limite de pages invalide")
    root = Path(allowed_root).resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    if not candidate.is_relative_to(root):
        raise PermissionError("PDF hors dossier autorisé")
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise PermissionError("Lien ou jonction interdit")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise PermissionError("PDF hors dossier autorisé")
    if resolved.suffix.casefold() != ".pdf":
        raise ValueError("Seuls les PDF sont autorisés")
    if resolved.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("PDF trop volumineux")
    with resolved.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise ValueError("En-tête PDF invalide")
        source.seek(0)
        from pypdf import PdfReader

        reader = PdfReader(source, strict=True)
        if reader.is_encrypted:
            raise ValueError("PDF chiffré non pris en charge")
        total = len(reader.pages)
        pages = []
        chars_left = MAX_CHARS
        truncated = total > max_pages
        for index in range(min(total, max_pages)):
            text = reader.pages[index].extract_text() or ""
            if len(text) > chars_left:
                text = text[:chars_left]
                truncated = True
            pages.append((index + 1, text))
            chars_left -= len(text)
            if chars_left == 0 and index + 1 < total:
                truncated = True
                break
    return ExtractedPDF(tuple(pages), total, truncated)
