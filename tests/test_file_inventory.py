"""ATLAS read-only file inventory tasks, isolated from the user's files."""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def isolated_profile(tmp_path, monkeypatch):
    """Redirect the actual file tool and the task path resolver to a test home."""
    from jarvis.tools.builtin import local_files

    expanduser = local_files.os.path.expanduser
    monkeypatch.setattr(
        local_files.os.path, "expanduser",
        lambda path: str(tmp_path) if path == "~" else expanduser(path),
    )
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def test_inventory_documents_runs_real_local_tool_not_llm(isolated_profile, monkeypatch):
    from jarvis import tasks

    root = isolated_profile / "Documents"
    root.mkdir()
    example = root / "rapport ATLAS.txt"
    example.write_text("Contenu confidentiel non transmis à l'IA", encoding="utf-8")
    (root / "Archives").mkdir()

    def forbid_model(*_args, **_kwargs):
        raise AssertionError("Une tâche directe ne doit pas invoquer le modèle")

    monkeypatch.setattr(tasks, "run_reply_engine", forbid_model)
    events = []
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
        event_callback=events.append,
    )
    try:
        task_id = manager.submit("Liste mes documents")
        manager.wait_for_idle(timeout=5)
        task = manager.get(task_id)
        assert task.status == tasks.TaskStatus.COMPLETED
        assert "Inventaire en lecture seule : Documents" in task.result
        assert "rapport ATLAS.txt" in task.result
        assert "Archives" in task.result
        assert "Contenu confidentiel non transmis" not in task.result
        assert example.read_text(encoding="utf-8") == (
            "Contenu confidentiel non transmis à l'IA"
        )
        assert [event["status"] for event in events] == [
            "queued", "running", "completed",
        ]
    finally:
        manager.shutdown()


def test_absent_documents_is_reported_as_failed(isolated_profile):
    from jarvis import tasks

    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        task_id = manager.submit("Liste mes documents")
        manager.wait_for_idle(timeout=5)
        task = manager.get(task_id)
        assert task.status == tasks.TaskStatus.FAILED
        assert task.result is None
        assert "Documents" in task.error
        assert not (isolated_profile / "Documents").exists()
    finally:
        manager.shutdown()


@pytest.mark.parametrize(
    ("prompt", "folder"),
    [
        ("Liste mes documents", "Documents"),
        ("Liste les fichiers de mes documents.", "Documents"),
        ("LISTE MES TÉLÉCHARGEMENTS !", "Downloads"),
        ("Liste les fichiers de mon bureau", "Desktop"),
        ("Supprime les fichiers de mes documents", None),
        ("Liste mes documents et efface les doublons", None),
        ("Liste mes documents du disque D:", None),
        ("Montre la liste des documents privés de mon voisin", None),
        ("Diagnostic système", None),
    ],
)
def test_inventory_routes_only_explicit_harmless_intents(prompt, folder):
    from jarvis.tasks import _direct_file_list_folder

    assert _direct_file_list_folder(prompt) == folder


def test_redirected_onedrive_inside_home_is_allowed(isolated_profile):
    from jarvis.tasks import _local_inventory_directory

    root = isolated_profile / "OneDrive" / "Documents"
    root.mkdir(parents=True)
    assert _local_inventory_directory("Documents") == root.resolve()


def test_external_onedrive_relocation_is_rejected(isolated_profile, monkeypatch):
    from jarvis.tasks import _local_inventory_directory

    external = isolated_profile.parent / "different-user-onedrive"
    monkeypatch.setenv("OneDrive", str(external))
    # The task must never browse outside the home sandbox even if a
    # Windows environment variable points elsewhere.
    external.mkdir(exist_ok=True)
    (external / "Downloads").mkdir(exist_ok=True)
    try:
        with pytest.raises(FileNotFoundError):
            _local_inventory_directory("Downloads")
    finally:
        (external / "Downloads").rmdir()
        external.rmdir()
