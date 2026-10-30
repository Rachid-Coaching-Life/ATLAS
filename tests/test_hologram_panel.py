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


def test_hologram_redraw_is_dormant_while_offline(qapp):
    """Static projection must not repaint on a perpetual timer when idle."""
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.show()
        qapp.processEvents()
        assert not panel._timer.isActive()
        panel.set_activity("idle")
        assert not panel._timer.isActive()
        panel.set_activity("listening")
        assert panel._timer.isActive()
        assert panel._timer.interval() >= 200
        panel.set_activity("thinking")
        assert panel._timer.isActive()
        panel.set_activity("asleep")
        assert not panel._timer.isActive()
        panel.set_activity("speaking")
        assert panel._timer.isActive()
        panel.hide()
        assert not panel._timer.isActive()
    finally:
        panel.close()


def test_projection_bridge_redraw_pauses_when_inactive(qapp):
    """Do not animate the energy bridge with no active assistant operation."""
    from desktop_app.hologram_panel import ProjectionBridge

    bridge = ProjectionBridge()
    try:
        bridge.show()
        qapp.processEvents()
        assert not bridge._timer.isActive()
        bridge.set_activity("listening")
        assert bridge._timer.isActive()
        assert bridge._timer.interval() >= 200
        bridge.set_activity("idle")
        assert not bridge._timer.isActive()
        bridge.set_activity("speaking")
        assert bridge._timer.isActive()
        bridge.hide()
        assert not bridge._timer.isActive()
    finally:
        bridge.close()


def test_premium_hologram_keeps_text_readable_and_glass_transparent(qapp):
    """Actual Qt render at desktop width with glyphs, no new graphics engine."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.show()
        qapp.processEvents()
        assert panel.heard.contentsMargins().left() == 43
        assert panel.reply.contentsMargins().left() == 43
        assert panel.heading.font().pointSize() == 11
        assert panel.status.font().pointSize() == 14
        assert panel.heard.geometry().width() > 260
        assert panel.voice_button.isVisible()
        assert panel.exchanges_button.isVisible()
        assert not panel._timer.isActive()  # no continuous idle graphics work

        canvas = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        panel.render(canvas)
        assert canvas.pixelColor(0, 0).alpha() == 0
        assert canvas.pixelColor(504, 0).alpha() == 0
        assert canvas.pixelColor(252, 165).alpha() > 0
        assert panel.input_region().contains(panel.voice_button.geometry().center())
    finally:
        panel.close()


def test_premium_hologram_compact_mode_omits_glyph_indent(qapp):
    """Keep real conversational text and controls legible on narrow screens."""
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(210, 205)
        panel.show()
        qapp.processEvents()
        assert panel.heard.contentsMargins().left() == 0
        assert panel.reply.contentsMargins().left() == 0
        assert panel.voice_button.isVisible()
        assert panel.exchanges_button.isVisible()
    finally:
        panel.close()


def test_offscreen_preview_loads_real_unicode_font_and_exports_png():
    """Regression: an offscreen Qt preview must not silently show square glyphs.

    The preview performs an actual proportional-glyph metrics check and saves
    only a detached PNG; it does not start the desktop app or voice daemon.
    """
    import os
    from pathlib import Path
    import subprocess
    import sys
    import tempfile
    from PyQt6.QtGui import QImage

    root = Path(__file__).resolve().parent.parent
    preview = root / "scripts" / "preview_atlas_hologram_offscreen.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [sys.executable, str(preview)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Police Qt hors écran :" in result.stdout
    assert "Prévisualisation ATLAS enregistrée :" in result.stdout

    image = QImage(str(Path(tempfile.gettempdir()) / "ATLAS_hologram_preview.png"))
    assert not image.isNull()
    assert image.width() == 505
    assert image.height() == 330
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(252, 165).alpha() > 0
    # Same genuine render on a simulated desktop background, not a mock-up.
    assert "Vue de contraste (fond simulé) :" in result.stdout
    backdrop = QImage(
        str(Path(tempfile.gettempdir()) / "ATLAS_hologram_sur_fond.png")
    )
    assert not backdrop.isNull()
    assert backdrop.size() == image.size()
    assert backdrop.pixelColor(0, 0).alpha() == 255

    # The same genuine Qt projection must also be legible on bright desktops.
    assert "Vue de lisibilité (fond clair simulé) :" in result.stdout
    daylight = QImage(
        str(Path(tempfile.gettempdir()) / "ATLAS_hologram_sur_fond_clair.png")
    )
    assert not daylight.isNull()
    assert daylight.size() == image.size()
    assert daylight.pixelColor(0, 0).alpha() == 255
    # Different backdrops, same actual HUD alpha and shape.
    assert daylight.pixelColor(0, 0) != backdrop.pixelColor(0, 0)


def test_spectral_layers_render_at_small_and_large_sizes(qapp):
    """Real Qt rendering of static spectral glass at both layout extremes.

    This is a widget/render regression test, not proof of GTR7 GPU stability.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    for width, height in ((210, 205), (505, 330)):
        panel = HologramPanel()
        try:
            panel.resize(width, height)
            panel.set_activity("idle")
            for state in ("idle", "listening", "speaking"):
                panel.set_activity(state)
                image = QImage(
                    panel.size(), QImage.Format.Format_ARGB32_Premultiplied
                )
                image.fill(0)
                panel.render(image)
                assert image.pixelColor(0, 0).alpha() == 0
                assert image.pixelColor(width - 1, 0).alpha() == 0
                assert image.pixelColor(width // 2, height // 2).alpha() > 0
            assert panel.heard.textFormat() == Qt.TextFormat.PlainText
            assert panel.reply.textFormat() == Qt.TextFormat.PlainText
        finally:
            panel.close()


def test_orbital_glass_emitter_respects_cutouts_and_idles_without_repaint(qapp, monkeypatch):
    """Check the normal 250-ms cadence independently of inherited shell modes."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    monkeypatch.delenv("ATLAS_HOLOGRAM_LOW_EFFECTS", raising=False)
    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.show()
        qapp.processEvents()
        assert not panel._timer.isActive()
        assert panel._timer.interval() == 250
        canvas = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        panel.render(canvas)
        # Hologram remains a shaped glass projection, not a solid widget box.
        assert canvas.pixelColor(0, 0).alpha() == 0
        assert canvas.pixelColor(504, 0).alpha() == 0
        assert canvas.pixelColor(252, 165).alpha() > 0
        assert canvas.pixelColor(470, 165).alpha() > 0

        panel.set_activity("listening")
        assert panel._timer.isActive()
        assert panel._timer.interval() == 250
        panel.set_activity("asleep")
        assert not panel._timer.isActive()
    finally:
        panel.close()


def test_new_hologram_instruments_skip_narrow_compact_geometry(qapp):
    """Detail embellishments cannot obscure the 210px mobile-style layout."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(210, 205)
        panel.show()
        qapp.processEvents()
        canvas = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        panel.render(canvas)
        assert canvas.pixelColor(0, 0).alpha() == 0
        assert canvas.pixelColor(105, 100).alpha() > 0
        assert panel.heard.text() == "Prononcez « Atlas » pour commencer."
        assert panel.voice_button.isVisible()
        assert panel.exchanges_button.isVisible()
    finally:
        panel.close()


def test_hologram_islands_leave_real_transparent_gap(qapp):
    """The new composition must not look like one tinted rectangular tablet.

    The gap between response and controls must transmit more of the desktop
    than the message glass while the title stays on a readable header island.
    """
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.show()
        qapp.processEvents()
        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)
        message_alpha = image.pixelColor(240, 188).alpha()
        # Sample the actual negative space, not the crossing telemetry line.
        gap_alpha = image.pixelColor(330, 251).alpha()
        title_alpha = image.pixelColor(240, 54).alpha()
        assert 155 <= message_alpha < 255
        assert gap_alpha < 80
        assert title_alpha >= 90
        assert image.pixelColor(0, 0).alpha() == 0
        assert not panel._timer.isActive()
    finally:
        panel.close()


def test_neural_emitter_lens_is_inside_panel_bounds(qapp):
    """The optical lens must be fully visible, not amputated at the right edge."""
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        center_x, radius = panel.emitter_lens_geometry()
        assert center_x - radius > 0
        assert center_x + radius < panel.width() - 3
    finally:
        panel.close()


def test_separated_hologram_islands_keep_open_negative_space(qapp):
    """Header, conversation and controls have distinct optical opacity.

    The visible result must no longer be one opaque background tablet.
    """
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.show()
        qapp.processEvents()
        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)
        # Between telemetry and the bottom control foot: truly open glass.
        negative_space = image.pixelColor(330, 251).alpha()
        message = panel.heard.geometry().center()
        button = panel.voice_button.geometry().center()
        message_alpha = image.pixelColor(message.x(), message.y()).alpha()
        button_alpha = image.pixelColor(button.x(), button.y()).alpha()
        assert negative_space < 85
        assert message_alpha > negative_space + 45
        assert button_alpha > negative_space + 45
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(504, 0).alpha() == 0
        assert not panel._timer.isActive()
    finally:
        panel.close()


def test_hologram_islands_keep_real_controls_and_compact_fallback(qapp, monkeypatch):
    """Default mode controls remain interactive regardless of shell settings."""
    from desktop_app.hologram_panel import HologramPanel

    monkeypatch.delenv("ATLAS_HOLOGRAM_LOW_EFFECTS", raising=False)
    for width, height in ((210, 205), (505, 330)):
        panel = HologramPanel()
        calls = []
        try:
            panel.resize(width, height)
            panel.show()
            qapp.processEvents()
            panel.voice_command_requested.connect(lambda: calls.append("voice"))
            panel.exchange_view_requested.connect(lambda: calls.append("exchanges"))
            assert panel.input_region().contains(panel.voice_button.geometry().center())
            assert panel.input_region().contains(panel.exchanges_button.geometry().center())
            panel.voice_button.click()
            panel.exchanges_button.click()
            assert calls == ["voice", "exchanges"]
            assert panel._timer.interval() == 250
            assert not panel._timer.isActive()
        finally:
            panel.close()


def test_opt_in_low_effects_keep_live_controls_and_portrait_geometry(qapp, monkeypatch):
    """The diagnostic reduces HUD work, not its essential functions or shape."""
    from PyQt6.QtGui import QImage
    from desktop_app.face_widget import FaceWindow
    from desktop_app.hologram_panel import HologramPanel, ProjectionBridge

    monkeypatch.setenv("ATLAS_HOLOGRAM_LOW_EFFECTS", "1")
    window = FaceWindow(hologram=True)
    try:
        panel = window.hologram
        bridge = window.bridge
        assert panel._low_effects
        assert bridge._low_effects
        assert panel._timer.interval() == 500
        assert bridge._timer.interval() == 500
        assert not window.face._portrait.isNull()
        assert window.face.width() > 0
        events = []
        panel.voice_command_requested.connect(lambda: events.append("voice"))
        panel.exchange_view_requested.connect(lambda: events.append("exchanges"))
        panel.voice_button.click()
        panel.exchanges_button.click()
        assert events == ["voice", "exchanges"]
        panel.show()
        qapp.processEvents()
        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(panel.width() // 2, panel.height() // 2).alpha() > 0
        panel.set_activity("idle")
        bridge.set_activity("idle")
        assert not panel._timer.isActive()
        assert not bridge._timer.isActive()
    finally:
        window.close()


def test_hologram_default_cadence_unchanged_without_diagnostic_opt_in(qapp, monkeypatch):
    from desktop_app.hologram_panel import HologramPanel, ProjectionBridge

    monkeypatch.delenv("ATLAS_HOLOGRAM_LOW_EFFECTS", raising=False)
    panel = HologramPanel()
    bridge = ProjectionBridge()
    try:
        assert not panel._low_effects
        assert not bridge._low_effects
        assert panel._timer.interval() == 250
        assert bridge._timer.interval() == 250
    finally:
        panel.close()
        bridge.close()


def test_offscreen_profiler_generates_json_without_native_desktop(tmp_path):
    """Regression: profile script must never start daemon, desktop or GPU API."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "profile_atlas_hologram_offscreen.py"
    output = tmp_path / "atlas_profile.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [sys.executable, str(script), "--samples", "2",
         "--warmup", "1", "--output", str(output)],
        cwd=root, env=env, capture_output=True, text=True, timeout=35,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert output.is_file()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["platform"] == "offscreen"
    assert data["samples"] == 2
    for name in (
        "hologram_normal_idle", "hologram_normal_listening",
        "hologram_alleger_idle", "hologram_alleger_listening",
        "hologram_hybride_idle", "hologram_hybride_listening",
        "bridge_normal_idle", "bridge_alleger_listening",
        "bridge_hybride_listening",
        "portrait_idle", "portrait_speaking",
    ):
        assert data["measurements"][name]["median_ms"] >= 0
    assert data["measurements"]["hologram_normal_listening"]["timer_ms"] == 250
    assert data["measurements"]["hologram_alleger_listening"]["timer_ms"] == 500


def test_hybrid_hologram_caches_static_light_and_keeps_real_controls(qapp, monkeypatch):
    """Cache build is once per size/DPR, including animated panel repaints."""
    from PyQt6.QtGui import QImage
    from desktop_app.hologram_panel import HologramPanel

    monkeypatch.setenv("ATLAS_HOLOGRAM_LOW_EFFECTS", "1")
    monkeypatch.setenv("ATLAS_HOLOGRAM_CACHED_EFFECTS", "1")
    panel = HologramPanel()
    events = []
    try:
        panel.resize(505, 330)
        panel.voice_command_requested.connect(lambda: events.append("voice"))
        panel.exchange_view_requested.connect(lambda: events.append("exchanges"))
        panel.show()
        qapp.processEvents()
        assert panel._cached_effects
        assert panel._low_effects
        assert panel._timer.interval() == 500
        first = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        first.fill(0)
        panel.render(first)
        assert panel._spectral_cache is not None
        key = panel._spectral_cache.cacheKey()
        cache = panel._spectral_cache
        again = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        again.fill(0)
        panel.render(again)
        assert panel._spectral_cache is cache
        assert panel._spectral_cache.cacheKey() == key
        assert first.pixelColor(0, 0).alpha() == 0
        assert first.pixelColor(252, 165).alpha() > 0
        panel.voice_button.click()
        panel.exchanges_button.click()
        assert events == ["voice", "exchanges"]

        panel.resize(420, 310)
        qapp.processEvents()
        resized = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        resized.fill(0)
        panel.render(resized)
        assert panel._spectral_cache_key[:2] == (420, 310)
        assert panel._spectral_cache is not cache
        panel.set_activity("idle")
        assert not panel._timer.isActive()
    finally:
        panel.close()


def test_hologram_cached_effects_are_opt_in(qapp, monkeypatch):
    """Unmodified normal rendering must allocate no spectral cache."""
    from desktop_app.hologram_panel import HologramPanel

    monkeypatch.delenv("ATLAS_HOLOGRAM_CACHED_EFFECTS", raising=False)
    monkeypatch.delenv("ATLAS_HOLOGRAM_LOW_EFFECTS", raising=False)
    panel = HologramPanel()
    try:
        assert not panel._cached_effects
        assert not panel._low_effects
        assert panel._timer.interval() == 250
        assert panel._spectral_cache is None
    finally:
        panel.close()


def test_card_upper_edges_stay_below_section_titles_at_both_sizes(qapp, monkeypatch):
    """Visible cyan/orange top rails must not strike their section captions."""
    from desktop_app.hologram_panel import HologramPanel

    # The geometry fix applies to all rendering modes, including the cached one.
    monkeypatch.setenv("ATLAS_HOLOGRAM_LOW_EFFECTS", "1")
    monkeypatch.setenv("ATLAS_HOLOGRAM_CACHED_EFFECTS", "1")
    for width, height in ((505, 330), (210, 205)):
        panel = HologramPanel()
        try:
            panel.resize(width, height)
            panel.show()
            qapp.processEvents()
            for caption, message in (
                (panel.heard_caption, panel.heard),
                (panel.reply_caption, panel.reply),
            ):
                rail_top = panel._glass_card_top(message)
                assert rail_top > caption.geometry().bottom()
                assert rail_top < message.geometry().top()
            assert panel.voice_button.isVisible()
            assert panel.exchanges_button.isVisible()
        finally:
            panel.close()


def test_hybrid_card_depth_rail_adds_optical_edge_without_layout_change(qapp, monkeypatch):
    """Compare the exact card-only raster with/without optional extrusion."""
    from PyQt6.QtGui import QColor, QImage, QPainter
    from desktop_app.hologram_panel import HologramPanel

    monkeypatch.setenv("ATLAS_HOLOGRAM_LOW_EFFECTS", "1")
    monkeypatch.setenv("ATLAS_HOLOGRAM_CACHED_EFFECTS", "1")
    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.show()
        qapp.processEvents()
        frame_size = panel.size()
        heard_rect = panel.heard.geometry()
        caption_bottom = panel.heard_caption.geometry().bottom()

        def render_card(extrusion):
            panel._cached_effects = extrusion
            image = QImage(frame_size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            try:
                panel._glass_card(painter, panel.heard, QColor(59, 209, 255),
                                  float(panel.width()))
            finally:
                painter.end()
            return image

        flat = render_card(False)
        deep = render_card(True)
        x = heard_rect.left() + 70
        y = heard_rect.bottom() + 7 + 4
        assert 0 <= x < frame_size.width()
        assert 0 <= y < frame_size.height()
        assert deep.pixelColor(x, y).alpha() > flat.pixelColor(x, y).alpha()
        assert panel._glass_card_top(panel.heard) > caption_bottom
        assert panel.heard.geometry() == heard_rect
        assert deep.pixelColor(0, 0).alpha() == 0
        assert panel._timer.interval() == 500
    finally:
        panel.close()
