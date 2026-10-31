"""Safety and extraction tests; isolated temporary documents only."""
from pathlib import Path

import pytest
from pypdf import PdfWriter

from jarvis.tools.builtin.pdf_extract import extract_pdf_text, MAX_PDF_BYTES


pytestmark = pytest.mark.unit


def _make_pdf(path: Path, pages=2):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    with path.open("wb") as handle:
        writer.write(handle)


def test_blank_pdf_returns_page_numbers_without_claiming_ocr(tmp_path):
    folder = tmp_path / "Documents"
    folder.mkdir()
    file = folder / "scan.pdf"
    _make_pdf(file)
    original = file.read_bytes()
    result = extract_pdf_text(file, folder)
    assert result.total_pages == 2
    assert result.pages == ((1, ""), (2, ""))
    assert not result.truncated
    assert file.read_bytes() == original


def test_page_budget_reports_partial_result(tmp_path):
    file = tmp_path / "pages.pdf"
    _make_pdf(file, pages=3)
    result = extract_pdf_text(file, tmp_path, max_pages=1)
    assert result.total_pages == 3
    assert result.pages == ((1, ""),)
    assert result.truncated


def test_rejects_corrupted_pdf(tmp_path):
    file = tmp_path / "corrupt.pdf"
    file.write_bytes(b"not a pdf")
    with pytest.raises(ValueError, match="En-tête PDF invalide"):
        extract_pdf_text(file, tmp_path)


def test_rejects_other_extensions(tmp_path):
    file = tmp_path / "notes.txt"
    file.write_bytes(b"%PDF-fake")
    with pytest.raises(ValueError, match="Seuls les PDF"):
        extract_pdf_text(file, tmp_path)


def test_rejects_outside_allowed_directory(tmp_path):
    allowed = tmp_path / "Documents"
    allowed.mkdir()
    outside = tmp_path / "secret.pdf"
    _make_pdf(outside)
    with pytest.raises(PermissionError):
        extract_pdf_text(outside, allowed)


def test_rejects_oversized_pdf(tmp_path):
    file = tmp_path / "large.pdf"
    with file.open("wb") as handle:
        handle.write(b"%PDF-")
        handle.seek(MAX_PDF_BYTES)
        handle.write(b"x")
    with pytest.raises(ValueError, match="trop volumineux"):
        extract_pdf_text(file, tmp_path)


def test_invalid_page_limit(tmp_path):
    with pytest.raises(ValueError, match="Limite de pages"):
        extract_pdf_text(tmp_path / "missing.pdf", tmp_path, max_pages=0)

def test_extracts_actual_text_from_page(tmp_path):
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    file = tmp_path / "texte.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 10 Td (Bonjour ATLAS) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with file.open("wb") as handle:
        writer.write(handle)

    result = extract_pdf_text(file, tmp_path)
    assert result.total_pages == 1
    assert "Bonjour ATLAS" in result.pages[0][1]
    assert result.truncated is False


def test_rejects_symbolic_link(tmp_path):
    real = tmp_path / "real.pdf"
    _make_pdf(real)
    link = tmp_path / "link.pdf"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Création de liens symboliques non autorisée sur ce système")
    with pytest.raises(PermissionError, match="Lien ou jonction"):
        extract_pdf_text(link, tmp_path)


def test_spoken_pdf_read_reuses_name_parser():
    from jarvis.tasks import _direct_spoken_pdf_read_request, _direct_voice_task_prompt

    assert _direct_spoken_pdf_read_request("Lis-moi mon contrat") == ("contrat", None)
    assert _direct_spoken_pdf_read_request("Lis moi ma facture sur le bureau") == ("facture", "Desktop")
    assert _direct_voice_task_prompt("ATLAS, lis-moi mon contrat") == "lis-moi mon contrat"
    assert _direct_spoken_pdf_read_request("Lis-moi mon contrat et supprime-le") is None


def test_read_named_pdf_does_not_open_viewer_or_call_model(tmp_path, monkeypatch):
    from jarvis import tasks
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    documents = tmp_path / "Documents"
    documents.mkdir()
    file = documents / "contrat.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font_ref = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 10 Td (Bonjour ATLAS) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with file.open("wb") as output:
        writer.write(output)
    before = file.read_bytes()
    monkeypatch.setattr(tasks, "_local_inventory_directory", lambda name: documents if name == "Documents" else tmp_path / name)
    monkeypatch.setattr(tasks.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(tasks.os, "startfile", lambda *_: pytest.fail("PDF viewer launched"), raising=False)
    monkeypatch.setattr(tasks, "run_reply_engine", lambda *_a, **_kw: pytest.fail("LLM called"))
    result = tasks._read_spoken_named_pdf("contrat", "Documents")
    assert "Bonjour ATLAS" in result
    assert "contrat.pdf" in result
    assert file.read_bytes() == before


def test_task_pdf_content_only_in_transient_voice_slot(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from jarvis import tasks

    secret = "DOCUMENT_TEST_SECRET_39495"
    records, events = [], []

    class DummyDb:
        def upsert_task_record(self, record):
            records.append(dict(record))

    monkeypatch.setattr(tasks, "_read_spoken_named_pdf", lambda *_: secret)
    manager = tasks.TaskManager(
        db=DummyDb(), cfg=SimpleNamespace(), dialogue_memory=None,
        event_callback=events.append,
    )
    try:
        identity = manager.submit("Lis-moi mon contrat")
        done = manager.wait_for_task(identity, timeout=5)
        assert done.status == tasks.TaskStatus.COMPLETED
        assert secret not in str(done.as_dict())
        assert secret not in str(records)
        assert secret not in str(events)
        assert secret not in capsys.readouterr().out
        assert manager.consume_private_speech(identity) == secret
        assert manager.consume_private_speech(identity) is None
    finally:
        manager.shutdown()
