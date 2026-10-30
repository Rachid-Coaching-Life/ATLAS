"""User controls on the live ATLAS projection, without altering the portrait."""

import pytest

pytestmark = pytest.mark.unit


def test_projected_voice_and_exchange_controls_are_clickable(qapp):
    from PyQt6.QtCore import Qt
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    events = []
    panel.voice_command_requested.connect(lambda: events.append("voice"))
    panel.exchange_view_requested.connect(lambda: events.append("exchanges"))
    try:
        panel.resize(320, 330)
        panel.show()
        qapp.processEvents()
        assert not panel.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert panel.voice_button.isVisible()
        assert panel.exchanges_button.isVisible()
        assert panel.voice_button.accessibleName()
        assert panel.exchanges_button.accessibleName()
        panel.voice_button.click()
        panel.exchanges_button.click()
        assert events == ["voice", "exchanges"]
    finally:
        panel.close()


def test_voice_control_only_displays_confirmed_status(qapp):
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.set_voice_control(running=False)
        assert panel.voice_button.isEnabled()
        assert "ACTIVER" in panel.voice_button.text()

        panel.set_voice_control(running=True, paused=False)
        assert panel.voice_button.isEnabled()
        assert "SUSPENDRE" in panel.voice_button.text()

        panel.set_voice_control(running=True, paused=True)
        assert "REPRENDRE" in panel.voice_button.text()

        panel.set_voice_control(running=True, paused=False, pending=True)
        assert not panel.voice_button.isEnabled()
        assert "EN COURS" in panel.voice_button.text()

        panel.set_voice_control(running=True, paused=None)
        assert "INCONNU" in panel.voice_button.text()

        panel.set_voice_control(running=True, available=False)
        assert not panel.voice_button.isEnabled()
    finally:
        panel.close()


def test_typed_queries_also_appear_in_last_exchange(qapp):
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.ingest_log("⌨️ Typed: Bonjour ATLAS <b>privé</b>\n")
        assert panel.heard.text() == "Bonjour ATLAS <b>privé</b>"
        panel.ingest_log("🔧 Tool call with unrelated text\n")
        assert panel.heard.text() == "Bonjour ATLAS <b>privé</b>"
    finally:
        panel.close()


def test_projection_voice_command_uses_existing_daemon_controls():
    from desktop_app.app import ATLASSystemTray

    tray = object.__new__(ATLASSystemTray)
    events = []
    tray.is_listening = False
    tray.toggle_listening = lambda: events.append("start")
    tray.toggle_voice_pause = lambda: events.append("pause_or_resume")

    tray._handle_hologram_voice_request()
    tray.is_listening = True
    tray._handle_hologram_voice_request()
    assert events == ["start", "pause_or_resume"]


def test_portrait_only_diagnostic_is_opt_in_and_preserves_atlas_art(qapp, monkeypatch):
    """Leave normal startup untouched; diagnostic removes only the projection."""
    from desktop_app.app import _diagnostic_hologram_enabled
    from desktop_app.face_widget import FaceWindow

    monkeypatch.delenv("ATLAS_DIAGNOSTIC_NO_HOLOGRAM", raising=False)
    assert _diagnostic_hologram_enabled() is True
    monkeypatch.setenv("ATLAS_DIAGNOSTIC_NO_HOLOGRAM", "0")
    assert _diagnostic_hologram_enabled() is True
    monkeypatch.setenv("ATLAS_DIAGNOSTIC_NO_HOLOGRAM", "1")
    assert _diagnostic_hologram_enabled() is False

    window = FaceWindow(hologram=_diagnostic_hologram_enabled())
    try:
        assert not window._hologram_enabled
        assert not hasattr(window, "hologram")
        assert not hasattr(window, "bridge")
        assert not window.face._portrait.isNull()
        assert window.windowTitle() == "🤖 ATLAS"
    finally:
        window.close()


def test_diagnostic_voice_autostart_is_opt_in(monkeypatch):
    """Default still starts voice; only exact diagnostic value 1 disables it."""
    from desktop_app.app import _diagnostic_autostart_enabled

    monkeypatch.delenv("ATLAS_DIAGNOSTIC_NO_AUTOSTART", raising=False)
    assert _diagnostic_autostart_enabled()
    monkeypatch.setenv("ATLAS_DIAGNOSTIC_NO_AUTOSTART", "0")
    assert _diagnostic_autostart_enabled()
    monkeypatch.setenv("ATLAS_DIAGNOSTIC_NO_AUTOSTART", "1")
    assert not _diagnostic_autostart_enabled()


def test_diagnostic_main_skips_setup_ollama_and_voice_before_start(qapp, monkeypatch):
    """Test the actual main() entry path, not just the flag helper."""
    import signal
    from desktop_app import app as desktop
    from desktop_app import splash_screen

    created = []
    events = []

    class FakeSplash:
        def show(self):
            events.append("splash")
        def set_status(self, value):
            events.append(("status", value))
        def close_splash(self):
            events.append("close_splash")

    class FakeTray:
        def __init__(self, *, ollama_runtime_ownership):
            assert ollama_runtime_ownership.process is None
            assert ollama_runtime_ownership.launch_method == ""
            created.append(self)
        def show_launch_windows(self):
            events.append("portrait")
        def start_daemon(self):
            pytest.fail("Diagnostic must not start the voice/AI daemon")
        def run(self):
            events.append("event_loop")
            return 0

    def forbid_process(*_args, **_kwargs):
        pytest.fail("Diagnostic must not launch Ollama or other processes")

    def forbid_setup(*_args, **_kwargs):
        pytest.fail("Diagnostic must skip Ollama/setup wizard checks")

    monkeypatch.setenv("ATLAS_DIAGNOSTIC_NO_HOLOGRAM", "1")
    monkeypatch.setenv("ATLAS_DIAGNOSTIC_NO_AUTOSTART", "1")
    monkeypatch.setattr(desktop, "acquire_single_instance_lock", lambda: True)
    monkeypatch.setattr(desktop, "check_previous_crash", lambda: False)
    monkeypatch.setattr(desktop, "setup_crash_logging", lambda: None)
    monkeypatch.setattr(desktop, "mark_session_started", lambda: None)
    monkeypatch.setattr(desktop, "mark_session_clean_exit", lambda: None)
    monkeypatch.setattr(desktop.atexit, "register", lambda callback: None)
    monkeypatch.setattr(signal, "signal", lambda *_args: None)
    monkeypatch.setattr(splash_screen, "SplashScreen", FakeSplash)
    monkeypatch.setattr(desktop, "ATLASSystemTray", FakeTray)
    monkeypatch.setattr(desktop, "SetupCheckWorker", forbid_setup)
    monkeypatch.setattr(desktop, "ServerCheckWorker", forbid_setup)
    monkeypatch.setattr(desktop.subprocess, "Popen", forbid_process)

    assert desktop.main() == 0
    assert len(created) == 1
    assert "portrait" in events
    assert "event_loop" in events
    assert events.index("close_splash") < events.index("portrait")


def test_hologram_can_stop_hidden_chat_query(qapp):
    """Stop a real queued chat turn without opening chat or stopping voice."""
    from types import SimpleNamespace
    from desktop_app.app import ATLASSystemTray
    from desktop_app.chat_window import ChatWindow
    from desktop_app.hologram_panel import HologramPanel

    sent, cancelled = [], []
    chat = ChatWindow(
        submit_fn=sent.append,
        cancel_fn=lambda: cancelled.append("chat_only"),
        daemon_available=True,
    )
    panel = HologramPanel()
    tray = object.__new__(ATLASSystemTray)
    tray.chat_window = chat
    tray.face_window = SimpleNamespace(
        _hologram_enabled=True,
        hologram=panel,
        ingest_chat_preview=panel.set_conversation_preview,
    )
    tray._connect_chat_to_hologram(chat)
    panel.stop_response_requested.connect(tray._handle_hologram_stop_request)
    try:
        panel.resize(430, 330)
        panel.show()
        qapp.processEvents()
        assert panel.stop_response_button.isHidden()
        assert not chat.isVisible()

        chat.input_widget.setPlainText("Quel est le statut de mon projet ?")
        chat._send()
        qapp.processEvents()
        assert sent == ["Quel est le statut de mon projet ?"]
        assert panel.stop_response_button.isVisible()
        assert panel.stop_response_button.isEnabled()
        assert panel.reply.text() == "ATLAS prépare sa réponse…"

        panel.stop_response_button.click()
        qapp.processEvents()
        assert cancelled == ["chat_only"]
        assert not chat._query_in_flight
        assert panel.stop_response_button.isHidden()
        assert panel.reply.text() == "Réponse interrompue."

        chat._on_complete("Réponse arrivée trop tard")
        assert panel.reply.text() == "Réponse interrompue."
        tray._handle_hologram_stop_request()
        assert cancelled == ["chat_only"]  # no duplicate cancellation
    finally:
        chat.close()
        panel.close()


def test_hologram_stop_follows_chat_completion_and_daemon_shutdown(qapp):
    from types import SimpleNamespace
    from desktop_app.app import ATLASSystemTray
    from desktop_app.chat_window import ChatWindow
    from desktop_app.hologram_panel import HologramPanel

    chat = ChatWindow(submit_fn=lambda text: None, daemon_available=True)
    panel = HologramPanel()
    tray = object.__new__(ATLASSystemTray)
    tray.chat_window = chat
    tray.face_window = SimpleNamespace(
        _hologram_enabled=True, hologram=panel,
        ingest_chat_preview=panel.set_conversation_preview,
    )
    tray._connect_chat_to_hologram(chat)
    try:
        panel.show()
        qapp.processEvents()
        chat.input_widget.setPlainText("Première demande")
        chat._send()
        assert not panel.stop_response_button.isHidden()
        chat._on_complete("Réponse finale")
        assert panel.stop_response_button.isHidden()
        assert panel.reply.text() == "Réponse finale"

        chat.input_widget.setPlainText("Deuxième demande")
        chat._send()
        assert not panel.stop_response_button.isHidden()
        chat.set_daemon_status("stopped")
        assert panel.stop_response_button.isHidden()
        assert not chat._query_in_flight
    finally:
        chat.close()
        panel.close()


def test_hologram_copy_action_uses_current_visible_plain_text(qapp):
    """No clipboard side effect until the user chooses Copy on a card."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    clipboard = qapp.clipboard()
    prior = clipboard.text()
    try:
        clipboard.setText("valeur témoin")
        panel.set_conversation_preview(
            "<b>Demande confidentielle</b>",
            "Réponse initiale",
        )
        assert clipboard.text() == "valeur témoin"
        assert panel.heard.textFormat() == Qt.TextFormat.PlainText
        assert panel.reply.textFormat() == Qt.TextFormat.PlainText

        for label in (panel.heard, panel.reply):
            assert label.contextMenuPolicy() == Qt.ContextMenuPolicy.ActionsContextMenu
            actions = label.findChildren(QAction, "atlas_hud_copy_visible_text")
            assert len(actions) == 1
            assert actions[0].text() == "Copier le texte affiché"

        panel.heard.actions()[0].trigger()
        assert clipboard.text() == "<b>Demande confidentielle</b>"

        # A single QAction always copies the latest displayed answer.
        panel.set_conversation_preview("Une autre demande", "Nouvelle réponse")
        assert clipboard.text() == "<b>Demande confidentielle</b>"
        panel.reply.actions()[0].trigger()
        assert clipboard.text() == "Nouvelle réponse"

        # Copy only the text truly displayed, never imply full long reply.
        panel.set_conversation_preview("Question", "x" * 300)
        panel.reply.actions()[0].trigger()
        assert clipboard.text() == "x" * 250
    finally:
        clipboard.setText(prior)
        panel.close()


def test_hologram_write_control_opens_focused_quick_input_without_full_chat(qapp, monkeypatch):
    """A real prompt is submitted through the shared hidden chat, not a new backend."""
    from types import SimpleNamespace
    from desktop_app.app import ATLASSystemTray
    from desktop_app.hologram_panel import HologramPanel

    monkeypatch.setattr("desktop_app.chat_window.get_hot_window_messages", lambda: [])
    sent = []
    panel = HologramPanel()
    tray = object.__new__(ATLASSystemTray)
    tray.is_listening = True
    tray.chat_window = None
    tray._chat_submit_fn = sent.append
    tray._chat_cancel_fn = lambda: None
    tray._chat_control_fn = lambda action, data: None
    tray._request_hologram_text = lambda: ("  Résume le projet ATLAS  ", True)
    tray.face_window = SimpleNamespace(
        _hologram_enabled=True,
        hologram=panel,
        ingest_chat_preview=panel.set_conversation_preview,
    )
    panel.text_input_requested.connect(tray._handle_hologram_text_request)
    try:
        panel.resize(430, 330)
        panel.show()
        qapp.processEvents()
        assert panel.write_button.isVisible()
        panel.write_button.click()
        qapp.processEvents()
        assert sent == ["Résume le projet ATLAS"]
        assert tray.chat_window is not None
        assert not tray.chat_window.isVisible()
        assert panel.heard.text() == "Résume le projet ATLAS"
        assert panel.reply.text() == "ATLAS prépare sa réponse…"
        assert panel.write_button.isHidden()
        assert panel.stop_response_button.isVisible()

        tray.chat_window._on_complete("Le projet est en cours.")
        qapp.processEvents()
        assert panel.reply.text() == "Le projet est en cours."
        assert panel.write_button.isVisible()
        assert panel.stop_response_button.isHidden()
    finally:
        if tray.chat_window is not None:
            tray.chat_window.close()
        panel.close()


def test_hologram_write_cancel_does_not_create_a_chat(qapp):
    from types import SimpleNamespace
    from desktop_app.app import ATLASSystemTray
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    tray = object.__new__(ATLASSystemTray)
    tray.is_listening = True
    tray.chat_window = None
    tray._request_hologram_text = lambda: ("question non envoyée", False)
    tray.face_window = SimpleNamespace(
        _hologram_enabled=True, hologram=panel,
        ingest_chat_preview=panel.set_conversation_preview,
    )
    try:
        tray._handle_hologram_text_request()
        assert tray.chat_window is None
        assert panel.heard.text() == "Prononcez « Atlas » pour commencer."
    finally:
        panel.close()


def test_hologram_write_button_keeps_compact_hud_and_busy_state(qapp):
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    events = []
    panel.text_input_requested.connect(lambda: events.append("write"))
    try:
        panel.resize(270, 240)
        panel.show()
        qapp.processEvents()
        assert panel.write_button.isVisible()
        assert panel.write_button.text() == "✎"
        assert panel.write_button.accessibleName() == "Écrire une demande à ATLAS"
        panel.write_button.click()
        assert events == ["write"]

        panel.set_chat_response_pending(True)
        assert panel.write_button.isHidden()
        assert panel.stop_response_button.isVisible()

        panel.set_chat_response_pending(False)
        assert panel.write_button.isVisible()
        assert panel.stop_response_button.isHidden()
        panel.resize(430, 330)
        qapp.processEvents()
        assert panel.write_button.text() == "ÉCRIRE"
    finally:
        panel.close()


def test_hologram_task_command_opens_existing_task_centre(qapp):
    """Use the one already-created task manager; no second agent or queue."""
    from types import SimpleNamespace
    from desktop_app.app import ATLASSystemTray
    from desktop_app.hologram_panel import HologramPanel

    called = []
    tray = object.__new__(ATLASSystemTray)
    tray.task_centre = SimpleNamespace(
        show=lambda: called.append("show"),
        raise_=lambda: called.append("raise"),
        activateWindow=lambda: called.append("activate"),
    )
    panel = HologramPanel()
    panel.task_view_requested.connect(tray.show_task_centre)
    try:
        panel.resize(450, 340)
        panel.show()
        qapp.processEvents()
        assert panel.task_button.text() == "TÂCHES"
        panel.task_button.click()
        assert called == ["show", "raise", "activate"]
        panel.resize(265, 240)
        qapp.processEvents()
        assert panel.task_button.text() == "TÂCH."
        assert panel.task_button.accessibleName() == "Ouvrir le centre des tâches ATLAS"
    finally:
        panel.close()


def test_hologram_quick_task_uses_real_centre_and_displays_confirmed_events(qapp):
    """Right-click action submits without opening a second queue or chat."""
    from types import SimpleNamespace
    from PyQt6.QtGui import QAction
    from desktop_app.app import ATLASSystemTray
    from desktop_app.hologram_panel import HologramPanel
    from desktop_app.task_centre import TaskCentreWindow

    admissions = []
    centre = TaskCentreWindow(
        lambda prompt, *, request_id: admissions.append((prompt, request_id)) or None,
        lambda task_id: None,
    )
    panel = HologramPanel()
    tray = object.__new__(ATLASSystemTray)
    tray.is_listening = True
    tray.task_centre = centre
    tray._request_hologram_task_text = lambda: ("  Contrôle les sauvegardes  ", True)
    panel.task_input_requested.connect(tray._handle_hologram_task_request)
    centre.task_submission_state_changed.connect(panel.set_task_submission_state)
    centre.task_updated.connect(panel.set_task_update)
    try:
        panel.resize(440, 330)
        panel.show()
        qapp.processEvents()
        actions = panel.task_button.findChildren(QAction, "atlas_hud_new_task")
        assert len(actions) == 1
        assert actions[0].text() == "Nouvelle tâche…"
        assert not centre.isVisible()
        centre.prompt.setPlainText("Brouillon du centre")
        actions[0].trigger()
        assert admissions[0][0] == "Contrôle les sauvegardes"
        assert centre.prompt.toPlainText() == "Brouillon du centre"
        assert not centre.isVisible()
        assert panel.heard_caption.text() == "INSTRUCTION DE TÂCHE"
        assert "Envoi au service" in panel.reply.text()

        # The GUI must never announce success before an actual task event.
        assert "terminé" not in panel.reply.text().lower()
        centre.add_or_update_task({
            "type": "task", "id": "atlas-1", "status": "queued",
            "prompt": "Contrôle les sauvegardes", "result": None, "error": None,
        })
        assert panel.reply.text() == "En attente d'exécution"
        centre.add_or_update_task({
            "type": "task", "id": "atlas-1", "status": "running",
            "prompt": "Contrôle les sauvegardes", "result": None, "error": None,
        })
        assert panel.reply.text() == "Exécution en cours"
        centre.add_or_update_task({
            "type": "task", "id": "atlas-1", "status": "completed",
            "prompt": "Contrôle les sauvegardes", "result": "Aucune erreur détectée",
            "error": None,
        })
        assert "Traitement terminé" in panel.reply.text()
        assert "Aucune erreur détectée" in panel.reply.text()
        assert "Aucune erreur détectée" in centre.details.toPlainText()

        centre.add_or_update_task({
            "type": "task", "id": "atlas-2", "status": "failed",
            "prompt": "Autre tâche", "result": None, "error": "Accès refusé",
        })
        assert panel.reply.text() == "Échec de la tâche — Accès refusé"
        panel.set_conversation_preview("Question vocale", "Réponse vocale")
        assert panel.reply_caption.text() == "RÉPONSE"
        assert panel.reply.text() == "Réponse vocale"
    finally:
        panel.close()
        centre.close()


def test_hologram_task_cancelled_quick_entry_does_not_submit(qapp):
    from desktop_app.app import ATLASSystemTray
    from desktop_app.task_centre import TaskCentreWindow

    received = []
    centre = TaskCentreWindow(
        lambda prompt, *, request_id: received.append(prompt) or "admitted",
        lambda task_id: None,
    )
    tray = object.__new__(ATLASSystemTray)
    tray.is_listening = True
    tray.task_centre = centre
    tray._request_hologram_task_text = lambda: ("Ne pas envoyer", False)
    try:
        tray._handle_hologram_task_request()
        assert received == []
        assert centre._pending_request is None
    finally:
        centre.close()
