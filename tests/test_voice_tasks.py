"""Spoken commands must execute tasks, not silently return to chatbot mode."""

from threading import RLock
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def test_profile(tmp_path, monkeypatch):
    from jarvis.tools.builtin import local_files

    expanduser = local_files.os.path.expanduser
    monkeypatch.setattr(
        local_files.os.path, "expanduser",
        lambda name: str(tmp_path) if name == "~" else expanduser(name),
    )
    for key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def _voice_fixture(task_manager, monkeypatch):
    from jarvis.listening.listener import VoiceListener
    from jarvis.listening.speech_context import SpeechContext
    from jarvis import activity

    listener = object.__new__(VoiceListener)
    listener.db = object()
    listener.cfg = SimpleNamespace(wake_word="atlas", wake_aliases=[])
    listener.dialogue_memory = None
    listener._task_manager = task_manager
    listener._pending_pdf_clarification = None
    listener._transcript_buffer = SimpleNamespace(
        get_last_seconds=lambda _seconds: [],
    )
    listener._buffer_duration = 30
    listener.echo_detector = SimpleNamespace(_last_tts_text="")
    listener._transcription_is_current = lambda _generation: True
    listener._clear_audio_buffers = lambda: None
    listener._stop_thinking_tune = lambda: None
    listener._audio_state_lock = RLock()
    hot_windows = []
    listener.activate_hot_window = lambda: hot_windows.append(True)

    speech = []
    class TTS:
        enabled = True

        def speak(self, message, completion_callback=None, terminal_callback=None):
            speech.append(message)
            if completion_callback:
                completion_callback()
            if terminal_callback:
                terminal_callback("completed")

    listener.tts = TTS()
    monkeypatch.setattr(
        SpeechContext, "capture",
        staticmethod(lambda *_args, **_kwargs: SimpleNamespace(segments=[])),
    )
    monkeypatch.setattr(
        activity, "get_jarvis_state",
        lambda: SimpleNamespace(
            acquire_state=lambda *_args, **_kwargs: object(),
            release_state=lambda _owner: True,
        ),
    )
    return listener, speech, hot_windows


def test_live_voice_query_routes_to_real_task_and_speaks_success(
    test_profile, monkeypatch,
):
    from jarvis import tasks
    from jarvis.listening.listener import VoiceListener
    from jarvis.reply import engine

    desktop = test_profile / "Desktop"
    desktop.mkdir()
    pdf = desktop / "Certificat-Medical-1&2.pdf"
    original = b"%PDF-1.7\nMedical test bytes"
    pdf.write_bytes(original)
    launched = []
    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    monkeypatch.setattr(
        engine, "run_reply_engine",
        lambda *_args, **_kwargs: pytest.fail(
            "La commande vocale directe ne doit pas invoquer le chatbot"
        ),
    )
    events = []
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
        event_callback=events.append,
    )
    try:
        voice, speech, hot_windows = _voice_fixture(manager, monkeypatch)
        VoiceListener._dispatch_query(
            voice, "ATLAS, ouvre mon certificat médical",
            language="fr", generation=3,
        )
        assert launched == [str(pdf.resolve())]
        assert speech == [
            "J'ai transmis la demande d'ouverture à Windows. "
            "Vérifiez que le lecteur PDF affiche le fichier."
        ]
        assert hot_windows == [True]
        assert events[-1]["status"] == "completed"
        assert pdf.read_bytes() == original
    finally:
        manager.shutdown()


def test_voice_ambiguity_asks_followup_then_uses_named_folder(
    test_profile, monkeypatch,
):
    from jarvis import tasks
    from jarvis.listening.listener import VoiceListener
    from jarvis.reply import engine

    for folder in ("Documents", "Desktop"):
        directory = test_profile / folder
        directory.mkdir()
        (directory / "Certificat-Medical.pdf").write_bytes(b"%PDF-1.7\n")

    launched = []
    monkeypatch.setattr(tasks.os, "startfile", launched.append, raising=False)
    monkeypatch.setattr(
        engine, "run_reply_engine",
        lambda *_args, **_kwargs: pytest.fail("Pas de traitement IA sur ce parcours"),
    )
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        voice, speech, hot_windows = _voice_fixture(manager, monkeypatch)
        VoiceListener._dispatch_query(
            voice, "Atlas ouvre mon certificat médical",
            language="fr", generation=2,
        )
        assert launched == []
        assert "Plusieurs PDF correspondent" in speech[0]
        assert voice._pending_pdf_clarification[0] == "certificat médical"
        assert hot_windows == [True]
        VoiceListener._dispatch_query(
            voice, "sur le Bureau", language="fr", generation=2,
        )
        assert launched == [
            str((test_profile / "Desktop" / "Certificat-Medical.pdf").resolve())
        ]
        assert len(speech) == 2
        assert voice._pending_pdf_clarification is None
    finally:
        manager.shutdown()


def test_non_task_voice_query_keeps_existing_reply_engine(
    test_profile, monkeypatch,
):
    from jarvis import tasks
    from jarvis.listening.listener import VoiceListener
    from jarvis.reply import engine

    requested = []
    def fake_reply(*args, **kwargs):
        requested.append((args[3], kwargs["language"]))
        return "Réponse ordinaire."

    monkeypatch.setattr(engine, "run_reply_engine", fake_reply)
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
    )
    try:
        voice, speech, _ = _voice_fixture(manager, monkeypatch)
        VoiceListener._dispatch_query(
            voice, "Atlas, explique-moi ce qu'est un PDF",
            language="fr", generation=1,
        )
        assert requested == [("Atlas, explique-moi ce qu'est un PDF", "fr")]
        assert speech == ["Réponse ordinaire."]
        assert manager.list_tasks() == []
    finally:
        manager.shutdown()


def test_voice_destructive_compound_file_request_fails_closed(
    test_profile, monkeypatch,
):
    from jarvis import tasks
    from jarvis.listening.listener import VoiceListener
    from jarvis.reply import engine

    (test_profile / "Desktop").mkdir()
    launches = []
    monkeypatch.setattr(tasks.os, "startfile", launches.append, raising=False)
    monkeypatch.setattr(
        engine, "run_reply_engine",
        lambda *_args, **_kwargs: pytest.fail(
            "Une commande fichier suspecte ne doit pas être confiée au chatbot"
        ),
    )
    events = []
    manager = tasks.TaskManager(
        db=object(), cfg=SimpleNamespace(), dialogue_memory=None,
        event_callback=events.append,
    )
    try:
        voice, speech, _ = _voice_fixture(manager, monkeypatch)
        VoiceListener._dispatch_query(
            voice, "ATLAS, ouvre mon certificat médical et supprime-le",
            language="fr", generation=1,
        )
        assert launches == []
        assert events[-1]["status"] == "failed"
        assert "Demande d'ouverture ambiguë" in speech[0]
    finally:
        manager.shutdown()
