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
