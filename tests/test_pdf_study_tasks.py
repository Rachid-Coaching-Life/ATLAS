"""Wiring of PDF study commands in the task manager (voice text, privacy, fail-closed)."""
from types import SimpleNamespace

import pytest

from jarvis import tasks
from jarvis.tools.builtin import pdf_study

pytestmark = pytest.mark.unit


class DummyDb:
    def __init__(self):
        self.records = []

    def upsert_task_record(self, record):
        self.records.append(dict(record))


def make_manager(events=None, **kwargs):
    db = DummyDb()
    manager = tasks.TaskManager(
        db=db, cfg=SimpleNamespace(), dialogue_memory=None,
        event_callback=(events.append if events is not None else None), **kwargs,
    )
    return manager, db


def no_engine(*_a, **_k):
    pytest.fail("the general reply engine must not run for PDF study commands")


@pytest.mark.parametrize("spoken,expected", [
    ("ATLAS, résume le PDF contrat", "résume le PDF contrat"),
    ("Atlas, dans le PDF contrat, quelle est la durée ?", "dans le PDF contrat, quelle est la durée ?"),
    ("ATLAS, lis-moi mon contrat", "lis-moi mon contrat"),
])
def test_voice_prompt_selects_study_and_read_tasks(spoken, expected):
    assert tasks._direct_voice_task_prompt(spoken) == expected


def test_unrelated_speech_is_not_a_direct_task():
    assert tasks._direct_voice_task_prompt("ATLAS, raconte-moi une blague") is None


def test_real_name_parser_gives_title_and_folder():
    parse = tasks._direct_spoken_pdf_request
    assert pdf_study.parse_summary_request("Résume le PDF contrat sur le bureau", parse) == ("contrat", "Desktop")
    assert pdf_study.parse_question_request(
        "Dans le PDF contrat dans mes documents, quelle est la durée ?", parse
    ) == ("contrat", "Documents", "quelle est la durée ?")
    assert pdf_study.parse_summary_request("Résume le PDF contrat et supprime-le", parse) is None


@pytest.mark.parametrize("prompt,expected", [
    ("Lis-moi mon contrat", True),
    ("Résume le PDF contrat", True),
    ("Dans le PDF contrat, quelle est la durée ?", True),
    ("Ouvre mon contrat", False),
    ("Quelle heure est-il", False),
    (None, False),
])
def test_private_pdf_task_predicate(prompt, expected):
    assert tasks._is_private_pdf_task(prompt) is expected


def test_study_result_only_in_transient_voice_slot(monkeypatch, capsys):
    secret = "DOCUMENT_STUDY_SECRET_77120"
    events = []
    monkeypatch.setattr(tasks, "_study_spoken_named_pdf", lambda *_a: secret)
    monkeypatch.setattr(tasks, "run_reply_engine", no_engine)
    manager, db = make_manager(events)
    try:
        identity = manager.submit("Résume le PDF contrat")
        done = manager.wait_for_task(identity, timeout=5)
        assert done.status == tasks.TaskStatus.COMPLETED
        assert "Réponse PDF préparée" in done.result
        assert secret not in str(done.as_dict())
        assert secret not in str(db.records)
        assert secret not in str(events)
        assert secret not in capsys.readouterr().out
        assert manager.consume_private_speech(identity) == secret
        assert manager.consume_private_speech(identity) is None
    finally:
        manager.shutdown()


def test_question_is_routed_with_title_folder_and_question(monkeypatch):
    seen = []
    monkeypatch.setattr(tasks, "_study_spoken_named_pdf", lambda *a: seen.append(a) or "ok")
    monkeypatch.setattr(tasks, "run_reply_engine", no_engine)
    manager, _db = make_manager()
    try:
        identity = manager.submit("Dans le PDF contrat sur le bureau, quelle est la durée ?")
        assert manager.wait_for_task(identity, timeout=5).status == tasks.TaskStatus.COMPLETED
        assert seen == [("contrat", "Desktop", "quelle est la durée ?", manager.cfg)]
    finally:
        manager.shutdown()


@pytest.mark.parametrize("prompt", [
    "Dans le PDF contrat quelle est la durée",
    "Résume le PDF contrat et supprime-le",
    "Résume le PDF contrat / Windows",
])
def test_malformed_study_commands_fail_closed(prompt, monkeypatch):
    monkeypatch.setattr(tasks, "_study_spoken_named_pdf",
                        lambda *_a: pytest.fail("must not study an ambiguous request"))
    monkeypatch.setattr(tasks, "run_reply_engine", no_engine)
    manager, _db = make_manager()
    try:
        identity = manager.submit(prompt)
        done = manager.wait_for_task(identity, timeout=5)
        assert done.status == tasks.TaskStatus.FAILED
        assert "ambiguë" in done.error
        assert manager.consume_private_speech(identity) is None
    finally:
        manager.shutdown()


def test_pruned_task_drops_its_private_speech(monkeypatch):
    monkeypatch.setattr(tasks, "_study_spoken_named_pdf", lambda *_a: "texte transitoire")
    manager, _db = make_manager(max_history=1)
    try:
        ids = []
        for _ in range(3):
            identity = manager.submit("Résume le PDF contrat")
            manager.wait_for_task(identity, timeout=5)
            ids.append(identity)
        assert manager.consume_private_speech(ids[0]) is None
    finally:
        manager.shutdown()


def test_shutdown_clears_private_speech_and_study_cache(monkeypatch):
    monkeypatch.setattr(tasks, "_study_spoken_named_pdf", lambda *_a: "texte transitoire")
    manager, _db = make_manager()
    identity = manager.submit("Résume le PDF contrat")
    manager.wait_for_task(identity, timeout=5)
    manager.shutdown()
    assert manager.consume_private_speech(identity) is None


def test_end_to_end_summary_on_a_real_pdf(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    pdf_extract = pytest.importorskip("jarvis.tools.builtin.pdf_extract")
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    documents = tmp_path / "Documents"
    documents.mkdir()
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=200)
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 9 Tf 5 100 Td (Le contrat prevoit une duree de douze mois renouvelable une fois.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with (documents / "contrat.pdf").open("wb") as handle:
        writer.write(handle)
    before = (documents / "contrat.pdf").read_bytes()
    monkeypatch.setattr(tasks, "_find_spoken_named_pdf", lambda *_a: ("Documents", ("contrat.pdf",)))
    monkeypatch.setattr(tasks, "_local_inventory_directory", lambda _folder: documents)
    text = tasks._study_spoken_named_pdf("contrat", "Documents", None, SimpleNamespace())
    assert "contrat.pdf" in text and "douze mois" in text
    assert (documents / "contrat.pdf").read_bytes() == before
