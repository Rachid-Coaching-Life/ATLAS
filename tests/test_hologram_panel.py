"""ATLAS portrait and holographic status must be a functional single Qt surface."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def test_hologram_displays_live_activity_and_safe_plaintext(qapp):
    from PyQt6.QtCore import Qt
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.set_activity("listening")
        assert panel.status.text() == "EN ÉCOUTE"
        panel.ingest_log('📝 Heard: "Atlas, ouvre mon dossier"\n')
        assert panel.heard.text() == "Atlas, ouvre mon dossier"
        panel.set_activity("thinking")
        assert panel.status.text() == "ANALYSE EN COURS"
        panel.ingest_log("🤖 ATLAS\n")
        panel.ingest_log("  Bonjour ! <b>Un texte, pas du HTML.</b>\n")
        assert panel.reply.text() == "Bonjour ! <b>Un texte, pas du HTML.</b>"
        assert panel.reply.textFormat() == Qt.TextFormat.PlainText
        panel.set_activity("speaking")
        assert "RÉPOND" in panel.status.text()
        panel.set_activity("idle")
        assert panel.status.text() == "À VOTRE SERVICE"
    finally:
        panel.close()


def test_hologram_rejects_ipc_and_nonconversation_logs(qapp):
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        previous = panel.heard.text(), panel.reply.text()
        panel.ingest_log("__CHAT__:{\"private\":true}\n")
        panel.ingest_log("🔧 Tools (llm): 2 selected\n")
        panel.ingest_log("⏱️ Traitement de la demande : 60 s\n")
        assert (panel.heard.text(), panel.reply.text()) == previous
    finally:
        panel.close()


def test_face_window_owns_panel_bridge_and_face(qapp):
    from PyQt6.QtCore import QPoint
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow(hologram=True)
    try:
        window.show()
        qapp.processEvents()
        assert window.face.parent() is window
        assert window.hologram.parent() is window
        assert window.bridge.parent() is window
        assert window.windowTitle() == "🤖 ATLAS"
        assert not window.hologram.geometry().isEmpty()
        assert window.mask().contains(window.hologram.geometry().center())
        window.ingest_log('📝 Heard: "Atlas, bonjour."')
        assert "Atlas, bonjour" in window.hologram.heard.text()
    finally:
        window.close()


def test_screen_geometry_keeps_projected_interface_onscreen(qapp):
    from PyQt6.QtCore import QRect
    from desktop_app.face_widget import FaceWindow

    for width, height in ((1920, 1080), (800, 600), (600, 900)):
        screen = SimpleNamespace(availableGeometry=lambda w=width, h=height: QRect(0, 0, w, h))
        with patch("desktop_app.face_widget.QApplication.primaryScreen", return_value=screen):
            window = FaceWindow(hologram=True)
        try:
            assert window.width() <= width
            assert window.height() <= height
            assert window._compact == (width < 740)
            assert window.hologram.width() > 0
            assert window.face.width() > 0
            assert window.bridge.width() > 0
        finally:
            window.close()
