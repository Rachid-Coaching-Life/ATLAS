"""Study mode for local PDFs: extractive summaries and sourced answers.

Read-only and local. Pure parsing helpers plus ``study_document``, which gets
its extractor and model call by injection so each part can be tested alone.
The document text lives only in a small in-memory cache and is never written
to disk, to the task history or to the logs.
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Tuple

from ...debug import debug_log
from . import pdf_qa
from .pdf_extract import STUDY_MAX_PAGES

EXTRACT_SECONDS = 10.0
MODEL_TIMEOUT_SEC = 20.0
MODEL_MAX_TOKENS = 250
CACHE_ENTRIES = 2
MAX_QUESTION_CHARS = 300

_DOC = r"(?:pdf|document|fichier)"
_SUMMARY_PREFIX = re.compile(
    r"^r[ée]sum[ée](?:-moi| moi)?\s+(?:le\s+)?" + _DOC + r"\s+", re.IGNORECASE)
_QUESTION_PREFIX = re.compile(r"^dans\s+(?:le\s+)?" + _DOC + r"\s+", re.IGNORECASE)

NameParser = Callable[[str], Optional[Tuple[str, Optional[str]]]]


def has_study_intent(prompt: Any) -> bool:
    """True for any summary/question phrasing, even a malformed one (fail closed)."""
    if not isinstance(prompt, str):
        return False
    text = prompt.strip()
    return bool(_SUMMARY_PREFIX.match(text) or _QUESTION_PREFIX.match(text))


def parse_summary_request(prompt: Any, parse_name: NameParser):
    """Return (title, folder_hint) for 'Résume le PDF <nom>' or None."""
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    match = _SUMMARY_PREFIX.match(text)
    if match is None:
        return None
    return parse_name("Ouvre mon " + text[match.end():])


def parse_question_request(prompt: Any, parse_name: NameParser):
    """Return (title, folder_hint, question) for 'Dans le PDF <nom>, <question>'."""
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    match = _QUESTION_PREFIX.match(text)
    if match is None:
        return None
    split = re.match(r"(.+?)\s*[,:]\s*(.+)$", text[match.end():], re.DOTALL)
    if split is None:
        return None
    question = " ".join(split.group(2).split())
    if not 3 <= len(question) <= MAX_QUESTION_CHARS:
        return None
    parsed = parse_name("Ouvre mon " + split.group(1))
    if parsed is None:
        return None
    return parsed[0], parsed[1], question


class _Cache:
    """Tiny in-memory LRU; keyed by file identity so edits invalidate it."""

    def __init__(self, entries: int) -> None:
        self._entries = entries
        self._items: "OrderedDict[tuple, Any]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key, value) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


_CACHE = _Cache(CACHE_ENTRIES)


def clear_cache() -> None:
    _CACHE.clear()


def ask_local_model(cfg: Any, question: str, passages: Sequence[pdf_qa.Passage], name: str) -> Optional[str]:
    """One bounded call to the local chat model; None when unavailable or remote."""
    base_url = getattr(cfg, "llm_base_url", "") or getattr(cfg, "ollama_base_url", "")
    if not pdf_qa.is_local_endpoint(base_url):
        debug_log("pdf study: model endpoint is not local, excerpts only", "tasks")
        return None
    try:
        from ...llm import Tier, get_llm_backend, resolve_model

        system, user = (m["content"] for m in pdf_qa.build_answer_messages(question, passages, name))
        return get_llm_backend(cfg).direct(
            resolve_model(cfg, Tier.CHAT), system, user,
            timeout_sec=MODEL_TIMEOUT_SEC, thinking=False, num_ctx=4096,
            temperature=0.0, max_tokens=MODEL_MAX_TOKENS,
        )
    except Exception as exc:
        debug_log(f"pdf study: model call failed ({type(exc).__name__})", "tasks")
        return None


def study_document(
    root: Path,
    relative: Path,
    question: Optional[str],
    cfg: Any,
    extract: Callable[..., Any],
    ask: Optional[Callable[..., Optional[str]]] = None,
) -> str:
    """Summarise (question is None) or answer from one validated local PDF."""
    ask = ask or ask_local_model
    candidate = Path(root) / relative
    meta = candidate.lstat()  # never follows a link
    key = (str(candidate), meta.st_mtime_ns, meta.st_size)
    extracted = _CACHE.get(key)
    if extracted is None:
        extracted = extract(
            relative, root, max_pages=STUDY_MAX_PAGES, study=True,
            deadline=time.monotonic() + EXTRACT_SECONDS,
        )
        _CACHE.put(key, extracted)
    pages = [(number, text) for number, text in extracted.pages if text.strip()]
    if not pages:
        raise ValueError("Ce PDF ne contient pas de texte extractible. Aucun OCR n'a été effectué.")
    name = Path(relative).name
    scope = pdf_qa.describe_scope(len(extracted.pages), extracted.total_pages, extracted.truncated)
    if question is None:
        return pdf_qa.format_summary(name, scope, pdf_qa.extractive_summary(pages))
    passages = pdf_qa.retrieve(pdf_qa.split_passages(pages), question)
    if not passages:
        return (f"Document {name}, {scope}. Aucun passage du document ne correspond à votre question. "
                f"{pdf_qa.NOT_IN_DOCUMENT}")
    return pdf_qa.format_answer(name, scope, passages, ask(cfg, question, passages, name))
