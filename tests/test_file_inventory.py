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


def test_direct_pdf_inventory_filters_without_loading_file_contents(isolated_profile, monkeypatch):
    from jarvis import tasks

    documents = isolated_profile / "Documents"
    documents.mkdir()
    pdf = documents / "attestation.pdf"
    pdf.write_bytes(b"%PDF-1.4\nPRIVATE PDF DATA\n")
    (documents / "liste.txt").write_text("texte prive", encoding="utf-8")
    nested = documents / "Archives"
    nested.mkdir()
    (nested / "ancien.pdf").write_bytes(b"%PDF-1.4\n")

    def forbid_model(*args, **kwargs):
        raise AssertionError("La liste de PDF ne doit pas appeler le modèle")

    monkeypatch.setattr(tasks, "run_reply_engine", forbid_model)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Liste les PDF de mes documents")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.COMPLETED
        assert "Inventaire en lecture seule : PDF du dossier Documents" in task.result
        assert "premier niveau uniquement" in task.result
        assert "attestation.pdf" in task.result
        assert "liste.txt" not in task.result
        assert "ancien.pdf" not in task.result
        assert "PRIVATE PDF DATA" not in task.result
        assert pdf.read_bytes().startswith(b"%PDF-1.4")
    finally:
        manager.shutdown()


def test_direct_pdf_inventory_no_match_is_a_valid_empty_result(isolated_profile):
    from jarvis import tasks

    downloads = isolated_profile / "Downloads"
    downloads.mkdir()
    (downloads / "notice.txt").write_text("texte", encoding="utf-8")
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Liste les PDF de mes téléchargements.")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.COMPLETED
        assert "No files found matching '*.pdf'" in task.result
    finally:
        manager.shutdown()


@pytest.mark.parametrize(
    ("prompt", "folder"),
    [
        ("Liste les PDF de mes documents", "Documents"),
        ("Liste les fichiers PDF de mes documents", "Documents"),
        ("LISTE LES PDF DE MES TÉLÉCHARGEMENTS !", "Downloads"),
        ("Liste les PDF de mon bureau.", "Desktop"),
        ("Cherche tous les PDF de mes documents et supprime les doublons", None),
        ("Liste les PDF de tout mon ordinateur", None),
        ("Liste les PDF du disque D", None),
        ("Ouvre chaque PDF et analyse son contenu", None),
        ("Liste mes documents", None),
    ],
)
def test_pdf_inventory_exact_intents_only(prompt, folder):
    from jarvis.tasks import _direct_pdf_list_folder

    assert _direct_pdf_list_folder(prompt) == folder


def test_recursive_pdf_search_reads_names_only_in_nested_folders(isolated_profile, monkeypatch):
    from jarvis import tasks

    root = isolated_profile / "Documents"
    nested = root / "Dossiers" / "Projet"
    nested.mkdir(parents=True)
    (root / "racine.pdf").write_bytes(b"PDF\nCONTENU PRIVE")
    (nested / "facture.PDF").write_bytes(b"PDF\nSECRET DE FACTURE")
    (nested / "notes.txt").write_text("Autre contenu", encoding="utf-8")

    def forbid_model(*args, **kwargs):
        raise AssertionError("Recherche directe : aucun modèle ne doit être appelé")

    monkeypatch.setattr(tasks, "run_reply_engine", forbid_model)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Recherche les PDF dans mes documents et sous-dossiers")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.COMPLETED
        assert "racine.pdf" in task.result
        assert "Dossiers" in task.result and "facture.PDF" in task.result
        assert "notes.txt" not in task.result
        assert "CONTENU PRIVE" not in task.result
        assert "SECRET DE FACTURE" not in task.result
        assert "Lecture seule" in task.result
        assert (nested / "facture.PDF").read_bytes() == b"PDF\nSECRET DE FACTURE"
    finally:
        manager.shutdown()


def test_bounded_pdf_search_reports_partial_when_entry_limit_hit(isolated_profile, monkeypatch):
    from jarvis.tools.builtin import local_files

    root = isolated_profile / "Downloads"
    root.mkdir()
    for index in range(8):
        (root / f"doc-{index}.pdf").write_bytes(b"PDF")
    monkeypatch.setattr(local_files, "_SEARCH_MAX_ENTRIES", 3)
    text = local_files._bounded_pdf_search(root, isolated_profile)
    assert "entrées inspectées : 3" in text
    assert "Recherche partielle" in text
    assert "limite d'entrées inspectées" in text


def test_bounded_pdf_search_does_not_follow_links(isolated_profile):
    from jarvis.tools.builtin import local_files

    root = isolated_profile / "Documents"
    root.mkdir()
    outside = isolated_profile.parent / "atlas-other-user-test"
    outside.mkdir(exist_ok=True)
    (outside / "secret.pdf").write_bytes(b"CONFIDENTIEL")
    shortcut = root / "raccourci"
    try:
        try:
            shortcut.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Ce Windows n'autorise pas les liens symboliques ici")
        text = local_files._bounded_pdf_search(root, isolated_profile)
        assert "secret.pdf" not in text
        assert "Recherche partielle" in text
        assert "ignorés/inaccessibles" in text
    finally:
        if shortcut.is_symlink():
            shortcut.unlink()
        (outside / "secret.pdf").unlink()
        outside.rmdir()


def test_bounded_pdf_search_rejects_outside_profile(isolated_profile):
    from jarvis.tools.builtin import local_files

    other = isolated_profile.parent / "atlas-outside-profile"
    other.mkdir(exist_ok=True)
    try:
        with pytest.raises(PermissionError):
            local_files._bounded_pdf_search(other, isolated_profile)
    finally:
        other.rmdir()


def test_bounded_pdf_search_rejects_other_file_types(isolated_profile):
    from jarvis.tools.builtin.local_files import LocalFilesTool

    root = isolated_profile / "Documents"
    root.mkdir()
    tool = LocalFilesTool()
    result = tool.run(
        {"operation": "search", "path": str(root), "file_type": "exe"},
        None,
    )
    assert result.success is False
    assert "PDF" in result.reply_text


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Recherche les PDF dans mes documents et sous-dossiers", "Documents"),
        ("Cherche les pdf dans mes téléchargements et sous dossiers", "Downloads"),
        ("Recherche les PDF dans mon bureau et sous-dossiers", "Desktop"),
        ("Recherche les PDF de tout mon PC", None),
        ("Recherche les PDF dans mes documents et supprime les anciens", None),
        ("Ouvre les PDF de mes documents", None),
        ("Recherche dans le dossier D: et ses sous-dossiers", None),
        ("Liste les PDF de mes documents", None),
    ],
)
def test_recursive_pdf_search_requires_exact_safe_command(prompt, expected):
    from jarvis.tasks import _direct_recursive_pdf_folder

    assert _direct_recursive_pdf_folder(prompt) == expected


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "expected"),
    [
        ("_SEARCH_MAX_DIRS", 1, "limite de dossiers"),
        ("_SEARCH_MAX_DEPTH", 0, "ignorés/inaccessibles"),
        ("_SEARCH_MAX_RESULTS", 1, "limite de résultats"),
    ],
)
def test_recursive_pdf_search_respects_other_budgets(
    isolated_profile, monkeypatch, limit_name, limit_value, expected,
):
    from jarvis.tools.builtin import local_files

    root = isolated_profile / "Documents"
    nested = root / "Alpha"
    nested.mkdir(parents=True)
    (root / "a.pdf").write_bytes(b"PDF")
    (nested / "b.pdf").write_bytes(b"PDF")
    monkeypatch.setattr(local_files, limit_name, limit_value)
    text = local_files._bounded_pdf_search(root, isolated_profile)
    assert "Recherche partielle" in text
    assert expected in text


def test_explicit_pdf_open_uses_windows_association_not_model(isolated_profile, monkeypatch):
    from jarvis import tasks

    nested = isolated_profile / "Documents" / "Archives"
    nested.mkdir(parents=True)
    target = nested / "facture 2026.pdf"
    original = b"%PDF-1.7\nDonnees de test"
    target.write_bytes(original)
    launched = []

    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    monkeypatch.setattr(
        tasks, "run_reply_engine",
        lambda *_args, **_kwargs: pytest.fail("Le moteur IA ne doit pas intervenir"),
    )
    events = []
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
        event_callback=events.append,
    )
    try:
        identity = manager.submit(r"Ouvre le PDF Documents\Archives\facture 2026.pdf")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.COMPLETED
        assert launched == [str(target.resolve())]
        assert "Demande d'ouverture transmise à Windows" in task.result
        assert "Vérifiez que votre lecteur PDF affiche le document" in task.result
        assert target.read_bytes() == original
        assert [item["status"] for item in events] == ["queued", "running", "completed"]
    finally:
        manager.shutdown()


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Ouvre le PDF Documents/rapport.pdf", ("Documents", ("rapport.pdf",))),
        (
            r"Ouvre le PDF Téléchargements\Factures\octobre.PDF",
            ("Downloads", ("Factures", "octobre.PDF")),
        ),
        ("ouvre le pdf Bureau/a.pdf", ("Desktop", ("a.pdf",))),
        ("Ouvre le PDF C:/Windows/rapport.pdf", None),
        (r"Ouvre le PDF \\serveur\partage\doc.pdf", None),
        ("Ouvre le PDF Documents/../Downloads/rapport.pdf", None),
        ("Ouvre le PDF Documents/rapport.docx", None),
        ("Ouvre le PDF Documents/rapport.pdf et supprime le fichier", None),
        ("Ouvre tous mes PDF", None),
        ("Ouvre le PDF Documents/rapport.pdf; rm -rf /", None),
        ("Ouvre le PDF Documents/rapport.pdf:payload", None),
        ("Ouvre le PDF Documents/rapport*.pdf", None),
        ("Ouvre le PDF Documents/rapport.pdf\nAutre commande", None),
        ("Liste les PDF de mes documents", None),
    ],
)
def test_explicit_pdf_open_parser_restricts_targets(prompt, expected):
    from jarvis.tasks import _direct_pdf_open_request

    assert _direct_pdf_open_request(prompt) == expected


@pytest.mark.parametrize(
    ("content", "expected_fragment"),
    [
        (b"Ce fichier n'est pas un PDF", "en-tête PDF valide"),
        (b"", "en-tête PDF valide"),
    ],
)
def test_bad_pdf_header_does_not_launch(
    isolated_profile, monkeypatch, content, expected_fragment,
):
    from jarvis import tasks

    root = isolated_profile / "Documents"
    root.mkdir()
    (root / "fausse.pdf").write_bytes(content)
    launched = []
    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Ouvre le PDF Documents/fausse.pdf")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.FAILED
        assert expected_fragment in task.error
        assert launched == []
    finally:
        manager.shutdown()


def test_missing_or_unapproved_pdf_does_not_launch(isolated_profile, monkeypatch):
    from jarvis import tasks

    (isolated_profile / "Documents").mkdir()
    launched = []
    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Ouvre le PDF Documents/introuvable.pdf")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.FAILED
        assert task.result is None
        assert launched == []
    finally:
        manager.shutdown()


def test_open_pdf_rejects_symlink_even_when_link_stays_inside_home(
    isolated_profile, monkeypatch,
):
    from jarvis import tasks

    root = isolated_profile / "Documents"
    root.mkdir()
    real = root / "vrai.pdf"
    real.write_bytes(b"%PDF-1.4")
    shortcut = root / "raccourci.pdf"
    try:
        shortcut.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Les liens symboliques ne sont pas disponibles sur Windows")
    launched = []
    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    try:
        with pytest.raises(PermissionError):
            tasks._open_explicit_local_pdf("Documents", ("raccourci.pdf",))
        assert launched == []
    finally:
        shortcut.unlink()


def test_windows_launch_error_marks_task_failed(isolated_profile, monkeypatch):
    from jarvis import tasks

    root = isolated_profile / "Documents"
    root.mkdir()
    (root / "fichier.pdf").write_bytes(b"%PDF-1.7\n")

    def failed_launch(_path):
        raise OSError("No PDF association configured")

    monkeypatch.setattr(tasks.os, "startfile", failed_launch, raising=False)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Ouvre le PDF Documents/fichier.pdf")
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.FAILED
        assert "No PDF association configured" in task.error
    finally:
        manager.shutdown()


@pytest.mark.parametrize(
    "instruction",
    [
        "Ouvre le PDF C:/Windows/secret.pdf",
        "Ouvre le PDF Documents/../Downloads/fichier.pdf",
        "Ouvre le PDF Documents/rapport.txt",
        "Ouvre le PDF Documents/rapport.pdf et supprime les autres",
    ],
)
def test_unsafe_pdf_open_request_fails_closed_without_llm(
    isolated_profile, monkeypatch, instruction,
):
    from jarvis import tasks

    documents = isolated_profile / "Documents"
    documents.mkdir()
    launched = []
    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    monkeypatch.setattr(
        tasks, "run_reply_engine",
        lambda *_args, **_kwargs: pytest.fail(
            "Un chemin PDF refusé ne doit jamais être transmis au moteur IA"
        ),
    )
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit(instruction)
        manager.wait_for_idle(timeout=5)
        task = manager.get(identity)
        assert task.status == tasks.TaskStatus.FAILED
        assert "Ouverture refusée" in task.error
        assert launched == []
    finally:
        manager.shutdown()


def test_spoken_pdf_title_opens_unique_matching_document(isolated_profile, monkeypatch):
    from jarvis import tasks

    desktop = isolated_profile / "Desktop"
    desktop.mkdir()
    original = b"%PDF-1.7\nProtected sample"
    named = desktop / "Certificat-Medical-1&2.pdf"
    named.write_bytes(original)
    (desktop / "Certificat-enregistrement.txt").write_text("other", encoding="utf-8")
    launches = []
    monkeypatch.setattr(tasks.os, "startfile", launches.append, raising=False)
    monkeypatch.setattr(
        tasks, "run_reply_engine",
        lambda *_args, **_kwargs: pytest.fail("Aucun appel au modèle IA autorisé"),
    )
    task_manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        voice_text = "ATLAS, ouvre mon certificat médical"
        command = tasks._direct_voice_task_prompt(voice_text, "atlas", [])
        assert command == "ouvre mon certificat médical"
        task_id = task_manager.submit(command)
        completed = task_manager.wait_for_task(task_id, timeout=5)
        assert completed.status == tasks.TaskStatus.COMPLETED
        assert launches == [str(named.resolve())]
        assert "transmise à Windows" in completed.result
        assert named.read_bytes() == original
    finally:
        task_manager.shutdown()


def test_spoken_pdf_ambiguous_name_never_opens(isolated_profile, monkeypatch):
    from jarvis import tasks

    for folder in ("Documents", "Desktop"):
        root = isolated_profile / folder
        root.mkdir()
        (root / "Certificat-Medical.pdf").write_bytes(b"%PDF-1.4")
    launches = []
    monkeypatch.setattr(tasks.os, "startfile", launches.append, raising=False)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Ouvre mon certificat médical")
        result = manager.wait_for_task(identity, timeout=5)
        assert result.status == tasks.TaskStatus.FAILED
        assert "Plusieurs PDF" in result.error
        assert "Précisez" in result.error
        assert launches == []
    finally:
        manager.shutdown()


def test_spoken_pdf_folder_qualifier_resolves_ambiguity(isolated_profile, monkeypatch):
    from jarvis import tasks

    for folder in ("Desktop", "Documents"):
        root = isolated_profile / folder
        root.mkdir()
        (root / "Certificat-Medical.pdf").write_bytes(b"%PDF-1.4")
    launches = []
    monkeypatch.setattr(tasks.os, "startfile", launches.append, raising=False)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Ouvre mon certificat médical sur le Bureau")
        result = manager.wait_for_task(identity, timeout=5)
        assert result.status == tasks.TaskStatus.COMPLETED
        assert launches == [
            str((isolated_profile / "Desktop" / "Certificat-Medical.pdf").resolve())
        ]
    finally:
        manager.shutdown()


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("ATLAS, ouvre mon certificat médical", "ouvre mon certificat médical"),
        ("Atlas ouvre mon certificat médical", "ouvre mon certificat médical"),
        ("ATLAS, Diagnostic système", "Diagnostic système"),
        ("ATLAS, liste mes documents", "liste mes documents"),
        ("ATLAS, recherche les PDF dans mes documents et sous-dossiers",
         "recherche les PDF dans mes documents et sous-dossiers"),
        ("ATLAS, ouvre le PDF Bureau/fichier.pdf",
         "ouvre le PDF Bureau/fichier.pdf"),
        ("ATLAS, explique moi la différence entre deux PDF", None),
        ("ATLAS, supprime tous les PDF", None),
        ("Un collègue a dit ATLAS, ouvre le fichier", None),
    ],
)
def test_voice_tasks_only_accept_existing_direct_intents(spoken, expected):
    from jarvis.tasks import _direct_voice_task_prompt

    assert _direct_voice_task_prompt(spoken, "atlas", ()) == expected


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("Ouvre mon certificat médical", ("certificat médical", None)),
        ("Ouvre mon certificat médical ?", ("certificat médical", None)),
        ("Ouvre mon certificat médical sur le bureau",
         ("certificat medical", "Desktop")),
        ("Ouvre mon certificat médical dans mes documents",
         ("certificat medical", "Documents")),
        ("Ouvre mon certificat médical et supprime-le", None),
        (r"Ouvre mon C:\Windows\secret.pdf", None),
        ("Ouvre mon navigateur", ("navigateur", None)),
    ],
)
def test_spoken_pdf_request_limits_actions(spoken, expected):
    from jarvis.tasks import _direct_spoken_pdf_request

    assert _direct_spoken_pdf_request(spoken) == expected


def test_spoken_pdf_missing_returns_failed_not_fabricated(isolated_profile, monkeypatch):
    from jarvis import tasks

    (isolated_profile / "Desktop").mkdir()
    launches = []
    monkeypatch.setattr(tasks.os, "startfile", launches.append, raising=False)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        identity = manager.submit("Ouvre mon certificat médical")
        result = manager.wait_for_task(identity, timeout=5)
        assert result.status == tasks.TaskStatus.FAILED
        assert "Aucun PDF correspondant" in result.error
        assert launches == []
    finally:
        manager.shutdown()
