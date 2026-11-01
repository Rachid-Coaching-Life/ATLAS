"""Tests for PDF study mode (summaries and sourced answers), on generated PDFs."""
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from jarvis.tools.builtin import pdf_qa, pdf_study
from jarvis.tools.builtin.pdf_extract import extract_pdf_text

pytestmark = pytest.mark.unit

PAGES = [
    "Le protocole TCP etablit une connexion fiable entre deux machines. La poignee de main en trois temps comprend les messages SYN, SYN-ACK puis ACK.",
    "Le protocole UDP n'etablit aucune connexion et ne garantit pas la livraison. On l'utilise pour la voix sur IP et le streaming video.",
    "Un pare-feu filtre le trafic reseau selon des regles. Il peut etre materiel ou logiciel et bloque des ports.",
]


def make_pdf(path: Path, texts):
    writer = PdfWriter()
    font_ref = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for text in texts:
        page = writer.add_blank_page(width=600, height=200)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
        })
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 9 Tf 5 100 Td ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


@pytest.fixture(autouse=True)
def fresh_cache():
    pdf_study.clear_cache()
    yield
    pdf_study.clear_cache()


@pytest.fixture
def course(tmp_path):
    folder = tmp_path / "Documents"
    folder.mkdir()
    make_pdf(folder / "reseaux.pdf", PAGES)
    return folder


def no_model(*_a, **_k):
    pytest.fail("model must not be called")


def test_extract_default_limits_unchanged_and_study_extends(tmp_path):
    make_pdf(tmp_path / "long.pdf", ["page"] * 25)
    with pytest.raises(ValueError, match="Limite de pages"):
        extract_pdf_text(tmp_path / "long.pdf", tmp_path, max_pages=25)
    result = extract_pdf_text(tmp_path / "long.pdf", tmp_path, max_pages=25, study=True)
    assert len(result.pages) == 25 and not result.truncated


def test_extract_deadline_returns_first_page_and_marks_partial(tmp_path):
    make_pdf(tmp_path / "long.pdf", ["page"] * 5)
    result = extract_pdf_text(tmp_path / "long.pdf", tmp_path, max_pages=5, study=True,
                              deadline=time.monotonic() - 1)
    assert len(result.pages) == 1 and result.truncated and result.total_pages == 5


def test_summary_is_extractive_with_pages_and_no_model(course):
    text = pdf_study.study_document(course, Path("reseaux.pdf"), None, SimpleNamespace(),
                                    extract_pdf_text, ask=no_model)
    assert "pas une reformulation" in text and "Page 1" in text
    assert "pages examinées : 3 sur 3" in text


def test_answer_is_backed_by_pages(course):
    def grounded(cfg, question, passages, name):
        assert all(p.page == 2 for p in passages[:1])
        return "UDP n'etablit aucune connexion et sert au streaming video [page 2]."
    text = pdf_study.study_document(course, Path("reseaux.pdf"), "Quel protocole sert au streaming video ?",
                                    SimpleNamespace(), extract_pdf_text, ask=grounded)
    assert text.startswith("Selon le document reseaux.pdf") and "page" in text


def test_invented_answer_falls_back_to_excerpts(course):
    text = pdf_study.study_document(
        course, Path("reseaux.pdf"), "Qu'est-ce qu'un pare-feu ?", SimpleNamespace(), extract_pdf_text,
        ask=lambda *a: "Le protocole QUIC chiffre toutes les donnees avec TLS depuis 2021.")
    assert "pas assez appuyée" in text and "Page 3" in text and "Selon le document" not in text


def test_model_unavailable_reads_excerpts(course):
    text = pdf_study.study_document(course, Path("reseaux.pdf"), "pare-feu", SimpleNamespace(),
                                    extract_pdf_text, ask=lambda *a: None)
    assert "extraits lus tels quels" in text and "Page 3" in text


def test_model_refusal_is_reported(course):
    text = pdf_study.study_document(course, Path("reseaux.pdf"), "pare-feu", SimpleNamespace(),
                                    extract_pdf_text, ask=lambda *a: pdf_qa.NOT_IN_DOCUMENT)
    assert pdf_qa.NOT_IN_DOCUMENT in text and "Selon le document" not in text


def test_unrelated_question_never_calls_model(course):
    text = pdf_study.study_document(course, Path("reseaux.pdf"), "recette de la tarte aux pommes",
                                    SimpleNamespace(), extract_pdf_text, ask=no_model)
    assert "Aucun passage" in text


def test_cache_reuses_extraction_and_detects_changes(course):
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return extract_pdf_text(*args, **kwargs)

    args = (course, Path("reseaux.pdf"), None, SimpleNamespace(), counting)
    pdf_study.study_document(*args)
    pdf_study.study_document(*args)
    assert len(calls) == 1
    make_pdf(course / "reseaux.pdf", PAGES + ["Une quatrieme page ajoutee avec du texte supplementaire ici."])
    pdf_study.study_document(*args)
    assert len(calls) == 2
    pdf_study.clear_cache()
    pdf_study.study_document(*args)
    assert len(calls) == 3


def test_scanned_pdf_reports_no_ocr(tmp_path):
    folder = tmp_path / "Documents"
    folder.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with (folder / "scan.pdf").open("wb") as handle:
        writer.write(handle)
    with pytest.raises(ValueError, match="Aucun OCR"):
        pdf_study.study_document(folder, Path("scan.pdf"), None, SimpleNamespace(), extract_pdf_text)


def test_source_pdf_is_not_modified(course):
    before = (course / "reseaux.pdf").read_bytes()
    pdf_study.study_document(course, Path("reseaux.pdf"), "pare-feu", SimpleNamespace(),
                             extract_pdf_text, ask=lambda *a: None)
    assert (course / "reseaux.pdf").read_bytes() == before


def parse_name(text):
    """Stand-in for tasks._direct_spoken_pdf_request."""
    name = text.removeprefix("Ouvre mon ").strip().rstrip(" .!?")
    if not name or " et " in f" {name} ":
        return None
    return (name, None)


def test_parsers_and_intent():
    assert pdf_study.parse_summary_request("Résume le PDF contrat", parse_name) == ("contrat", None)
    assert pdf_study.parse_summary_request("Résume-moi le document facture", parse_name) == ("facture", None)
    assert pdf_study.parse_summary_request("Résume le PDF contrat et supprime-le", parse_name) is None
    assert pdf_study.parse_question_request(
        "Dans le PDF contrat, quelle est la durée ?", parse_name) == ("contrat", None, "quelle est la durée ?")
    assert pdf_study.parse_question_request("Dans le PDF contrat quelle est la durée", parse_name) is None
    assert pdf_study.has_study_intent("Dans le PDF contrat quelle est la durée")
    assert pdf_study.has_study_intent("résumé le pdf contrat")
    assert not pdf_study.has_study_intent("Ouvre mon contrat")
    assert not pdf_study.has_study_intent(None)


def test_question_length_limit():
    long_question = "x" * 400
    assert pdf_study.parse_question_request(f"Dans le PDF a, {long_question}", parse_name) is None


def test_remote_endpoint_never_receives_document(monkeypatch):
    cfg = SimpleNamespace(llm_base_url="https://api.example.com/v1", ollama_base_url="")
    passages = [pdf_qa.Passage(1, "texte")]
    assert pdf_study.ask_local_model(cfg, "question", passages, "x.pdf") is None
