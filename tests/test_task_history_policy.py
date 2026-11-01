"""Task history is session-only by default; duplicate search is a direct read-only task."""
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis import tasks
from jarvis.tasks import TaskManager, TaskStatus

pytestmark = pytest.mark.unit


class SpyDb:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.upserts = []
        self.restores = 0
        self.prunes = []

    def upsert_task_record(self, record):
        self.upserts.append(dict(record))

    def get_task_records(self):
        self.restores += 1
        return self.rows

    def prune_task_records(self, keep):
        self.prunes.append(keep)


@pytest.fixture(autouse=True)
def no_history_env(monkeypatch):
    monkeypatch.delenv("ATLAS_TASK_HISTORY", raising=False)


def run_one(manager, prompt="Une demande"):
    with patch("jarvis.tasks.run_reply_engine", return_value="Fait"):
        identity = manager.submit(prompt)
        manager.wait_for_idle(timeout=2)
    return identity


def test_default_keeps_no_history_and_erases_the_old_one():
    db = SpyDb(rows=[{"id": "old"}])
    events = []
    manager = TaskManager(db, SimpleNamespace(), object(), event_callback=events.append)
    try:
        identity = run_one(manager)
        assert db.restores == 0
        assert db.upserts == []
        assert db.prunes[0] == 0
        assert manager.get(identity).status is TaskStatus.COMPLETED
        assert events[-1]["status"] == "completed"
    finally:
        manager.shutdown()


def test_explicit_opt_in_saves_and_restores():
    row = dict(id="kept", prompt="Ancienne", status="completed", result="ok",
               error=None, created_at=1.0, started_at=1.0, completed_at=2.0)
    db = SpyDb(rows=[row])
    manager = TaskManager(db, SimpleNamespace(), object(), persist_history=True)
    try:
        assert manager.get("kept").result == "ok"
        run_one(manager)
        assert db.upserts
        assert 0 not in db.prunes
    finally:
        manager.shutdown()


def test_environment_opt_in(monkeypatch):
    monkeypatch.setenv("ATLAS_TASK_HISTORY", "1")
    db = SpyDb()
    manager = TaskManager(db, SimpleNamespace(), object())
    try:
        run_one(manager)
        assert db.upserts and db.restores == 1
    finally:
        manager.shutdown()


@pytest.mark.parametrize("value", ["0", "", "true", "yes"])
def test_other_environment_values_do_not_enable_history(monkeypatch, value):
    monkeypatch.setenv("ATLAS_TASK_HISTORY", value)
    db = SpyDb()
    manager = TaskManager(db, SimpleNamespace(), object())
    try:
        run_one(manager)
        assert db.upserts == [] and db.restores == 0
    finally:
        manager.shutdown()


def test_explicit_false_beats_the_environment(monkeypatch):
    monkeypatch.setenv("ATLAS_TASK_HISTORY", "1")
    db = SpyDb()
    manager = TaskManager(db, SimpleNamespace(), object(), persist_history=False)
    try:
        run_one(manager)
        assert db.upserts == [] and db.restores == 0
    finally:
        manager.shutdown()


def test_cleanup_failure_never_blocks_startup():
    class Broken(SpyDb):
        def prune_task_records(self, keep):
            raise RuntimeError("token=synthetic-secret")

    manager = TaskManager(Broken(), SimpleNamespace(), object())
    try:
        assert run_one(manager)
    finally:
        manager.shutdown()


@pytest.mark.parametrize("spoken,folder", [
    ("ATLAS, cherche les doublons dans mes documents", "Documents"),
    ("Atlas, recherche les doublons dans mes téléchargements", "Downloads"),
    ("Atlas trouve les doublons sur le bureau", "Desktop"),
    ("Atlas, trouve les doublons dans mon bureau.", "Desktop"),
])
def test_duplicate_commands_are_direct_tasks(spoken, folder):
    clean = tasks._direct_voice_task_prompt(spoken)
    assert clean is not None
    assert tasks._direct_duplicate_folder(clean) == folder


@pytest.mark.parametrize("spoken", [
    "Atlas, cherche les doublons dans mes documents et supprime-les",
    "Atlas, supprime les doublons dans mes documents",
    "Atlas, cherche les doublons partout",
    "Atlas, cherche les doublons dans C:\\Windows",
])
def test_unsafe_or_vague_duplicate_requests_are_not_direct_tasks(spoken):
    assert tasks._direct_duplicate_folder(spoken) is None
    assert tasks._direct_voice_task_prompt(spoken) is None


def test_duplicate_task_reports_without_touching_files(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    (docs / "a.bin").write_bytes(b"Z" * 4096)
    (docs / "copie.bin").write_bytes(b"Z" * 4096)
    before = sorted(p.name for p in docs.iterdir())
    monkeypatch.setattr(tasks, "_local_inventory_directory", lambda _folder: docs)
    monkeypatch.setattr(tasks, "run_reply_engine",
                        lambda *_a, **_k: pytest.fail("duplicate search must not use the model"))
    manager = TaskManager(object(), SimpleNamespace(), object())
    try:
        identity = manager.submit("Cherche les doublons dans mes documents")
        done = manager.wait_for_task(identity, timeout=5)
        assert done.status is TaskStatus.COMPLETED
        assert "a.bin" in done.result and "copie.bin" in done.result
        assert "Aucun fichier n'a été modifié" in done.result
        assert sorted(p.name for p in docs.iterdir()) == before
    finally:
        manager.shutdown()
