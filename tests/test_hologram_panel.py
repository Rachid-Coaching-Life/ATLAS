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


def test_repeated_hologram_mask_refresh_is_idempotent(qapp, monkeypatch):
    """Repeated Qt geometry events must not endlessly reapply native masks."""
    from unittest.mock import MagicMock
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow(hologram=True)
    native_mask = MagicMock()
    monkeypatch.setattr(window, "setMask", native_mask)
    try:
        window._refresh_mask()
        assert native_mask.call_count == 1
        window._refresh_mask()
        assert native_mask.call_count == 1

        # Simulate a native resize notification while applying that mask.
        window._last_composite_mask_geometry = None
        nested = False

        def resize_during_mask(region):
            nonlocal nested
            if not nested:
                nested = True
                window._refresh_mask()

        native_mask.side_effect = resize_during_mask
        window._refresh_mask()
        assert native_mask.call_count == 2
    finally:
        window.close()


def test_mask_updates_are_coalesced_before_event_loop_runs(qapp, monkeypatch):
    """At most one zero-delay Qt callback is queued for a burst of resizes."""
    from desktop_app import face_widget
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow(hologram=True)
    scheduled = []
    # Patch the module's timer factory, not the Qt C++ wrapper type itself.
    # Qt static methods can be read-only on some PyQt6 Windows builds.
    monkeypatch.setattr(
        face_widget, "QTimer",
        SimpleNamespace(singleShot=lambda delay, callback: scheduled.append((delay, callback))),
    )
    try:
        window._queue_mask_refresh()
        window._queue_mask_refresh()
        window._queue_mask_refresh()
        assert len(scheduled) == 1
        assert scheduled[0][0] == 0
        # A hidden window does not apply a native mask.
        scheduled[0][1]()
        assert window._mask_refresh_queued is False
    finally:
        window.close()


def test_holographic_mask_never_converts_alpha_bitmap(qapp, monkeypatch):
    """The joined HUD uses cheap widget hit regions; portrait pixels stay RGBA."""
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow(hologram=True)
    try:
        monkeypatch.setattr(
            window.face, "portrait_input_region",
            lambda *_args: (_ for _ in ()).throw(AssertionError("expensive alpha mask")),
        )
        window._refresh_mask()
        region = window.mask()
        assert not region.isEmpty()
        assert region.contains(window.hologram.geometry().center())
    finally:
        window.close()


def test_hologram_panel_paints_gradient_with_qt_float_geometry(qapp):
    """Regression: QPoint endpoints once crashed Qt inside paintEvent."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel, ProjectionBridge

    panel = HologramPanel()
    bridge = ProjectionBridge()
    try:
        panel.resize(320, 270)
        canvas = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        # Render the real Qt widget, not a mocked paintEvent; PyQt6 overload
        # mismatches raise only when QWidget actually paints.
        panel.render(canvas)
        # The new structure is truly nonrectangular. Its corners are
        # transparent; the central glass has a nonzero but partial alpha.
        assert canvas.pixelColor(2, 2).alpha() == 0
        assert canvas.pixelColor(315, 2).alpha() == 0
        assert 0 < canvas.pixelColor(80, 50).alpha() < 245
        assert panel.input_region().contains(panel.rect().center())
        assert not panel.input_region().contains(panel.rect().topLeft())

        bridge.resize(47, 270)
        link = QImage(bridge.size(), QImage.Format.Format_ARGB32_Premultiplied)
        link.fill(0)
        bridge.render(link)
        assert not link.isNull()
    finally:
        panel.close()
        bridge.close()


def test_sculptural_hologram_is_an_actual_cutout_not_rounded_rectangle(qapp):
    """Prove concave emitter geometry and transparent corner hit-testing."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(375, 330)
        shape = panel.projection_shape()
        region = panel.input_region()
        assert not region.isEmpty()
        assert not region.contains(QPoint(0, 0))
        assert not region.contains(QPoint(374, 0))
        assert not region.contains(QPoint(0, 329))
        assert not region.contains(QPoint(374, 329))
        assert region.contains(QPoint(187, 160))
        assert region.contains(QPoint(370, 164))  # emitter's central tip
        assert not region.contains(QPoint(370, 115))  # concave right cutout

        canvas = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        panel.render(canvas)
        assert canvas.pixelColor(0, 0).alpha() == 0
        assert canvas.pixelColor(374, 0).alpha() == 0
        assert canvas.pixelColor(187, 160).alpha() > 0
        assert shape.boundingRect().width() <= panel.width()
    finally:
        panel.close()


def test_holographic_skin_does_not_change_robot_geometry_or_portrait(qapp):
    """The new visual design is confined to the left-side HUD and bridge."""
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow(hologram=True)
    try:
        portrait = window.face._portrait
        face_rect = window.face.geometry()
        before = portrait.toImage()
        assert not portrait.isNull()
        assert window.bridge.width() == 47 or window._compact
        assert face_rect.width() == window.face.width()
        assert face_rect.height() == window.face.height()
        window.hologram.set_activity("listening")
        window.ingest_log('📝 Heard: "ATLAS, bonjour"')
        window.hologram.repaint()
        window.bridge.repaint()
        assert window.face.geometry() == face_rect
        assert window.face._portrait.toImage() == before
    finally:
        window.close()


def test_holographic_overlay_on_narrow_screen_remains_transparent(qapp):
    """The same polygon and legible labels work at the minimum 210px width."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(210, 205)
        panel.set_activity("speaking")
        panel.ingest_log('📝 Heard: "Présente-toi, Atlas"')
        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)
        assert image.pixelColor(0, 0).alpha() == 0
        assert panel.status.text() == "ATLAS VOUS RÉPOND"
        assert panel.heard.text() == "Présente-toi, Atlas"
        assert image.pixelColor(105, 100).alpha() > 0
    finally:
        panel.close()


def test_wide_neural_projection_preserves_portrait_screen_anchor(qapp):
    """A wider glass HUD must not move or resize ATLAS on large displays."""
    from PyQt6.QtCore import QRect
    from desktop_app.face_widget import FaceWindow

    desktop = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 1920, 1080))
    with patch("desktop_app.face_widget.QApplication.primaryScreen", return_value=desktop):
        window = FaceWindow(hologram=True)
        try:
            window.show()
            qapp.processEvents()
            window.layout().activate()
            assert window.hologram.width() == 505
            assert window.face.height() == 330
            assert window.width() <= 1920
            # Right-side screen positioning remains tied to the face, not HUD width.
            assert window.pos().x() + window.face.x() == (
                desktop.availableGeometry().right() - window.face.width() - 20
            )
        finally:
            window.close()


def test_neural_light_rails_keep_real_glass_cutouts(qapp):
    """The extra layers must not paint into the transparent desktop corners."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.set_activity("listening")
        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(504, 0).alpha() == 0
        assert image.pixelColor(252, 165).alpha() > 0
        assert image.pixelColor(262, 317).alpha() > 0  # optical emitter
        assert panel.input_region().contains(panel.voice_button.geometry().center())
    finally:
        panel.close()
