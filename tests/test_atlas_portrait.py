"""Regression checks for the installed ATLAS face image and its Qt host."""

from pathlib import Path

import pytest

ASSET = Path(__file__).resolve().parents[1] / (
    "src/desktop_app/desktop_assets/atlas_portrait.png"
)


@pytest.mark.unit
def test_atlas_portrait_is_a_valid_transparent_png():
    from PIL import Image

    assert ASSET.is_file()
    with Image.open(ASSET) as portrait:
        assert portrait.format == "PNG"
        assert portrait.width >= 200
        assert portrait.height >= 200
        assert "A" in portrait.convert("RGBA").getbands()
        alpha = portrait.convert("RGBA").getchannel("A")
        min_alpha, max_alpha = alpha.getextrema()
        assert min_alpha == 0
        assert max_alpha >= 200


@pytest.mark.unit
def test_atlas_face_widget_loads_portrait_and_keeps_a_clickable_region(qapp):
    from PyQt6.QtCore import QPoint
    from desktop_app.face_widget import FaceWidget

    face = FaceWidget()
    assert not face._portrait.isNull()
    assert face._portrait.hasAlphaChannel()
    region = face.portrait_input_region(280, 280)
    assert not region.isEmpty()
    assert region.contains(QPoint(140, 100))
    assert not region.contains(QPoint(0, 0))
    face.close()


@pytest.mark.unit
def test_face_window_has_atlas_identity_and_portrait(qapp):
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow()
    try:
        assert window.windowTitle() == "🤖 ATLAS"
        assert not window.face._portrait.isNull()
        image = window.face._portrait
        assert window.width() == max(200, round(280 * image.width() / image.height()))
        assert window.height() == 280
    finally:
        window.close()


@pytest.mark.unit
def test_splash_screen_displays_atlas_identity(qapp):
    from PyQt6.QtWidgets import QLabel
    from desktop_app.splash_screen import SplashScreen

    splash = SplashScreen()
    try:
        assert "ATLAS" in [label.text() for label in splash.findChildren(QLabel)]
    finally:
        splash.close_splash()


@pytest.mark.unit
def test_non_square_portrait_does_not_stretch(qapp):
    """A tall official portrait must retain its aspect ratio in the Qt canvas."""
    from desktop_app.face_widget import FaceWidget

    result = FaceWidget._portrait_bounds(240, 280, 1145, 1373)
    assert result.width() <= 240
    assert result.height() <= 280
    assert abs(result.width() / result.height() - 1145 / 1373) < 0.0001
    assert abs(result.center().x() - 120) < 0.0001
    assert abs(result.center().y() - 140) < 0.0001


@pytest.mark.unit
def test_portrait_lips_move_only_during_speaking(qapp):
    """The new photo must visibly articulate; an idle portrait remains still."""
    from PyQt6.QtGui import QImage, QPainter
    from desktop_app.face_widget import FaceWidget

    face = FaceWidget()
    face.resize(240, 280)
    face._elapsed = 1.37

    def paint(speaking):
        face._speaking = speaking
        frame = QImage(240, 280, QImage.Format.Format_ARGB32_Premultiplied)
        frame.fill(0)
        painter = QPainter(frame)
        try:
            face._paint_portrait(painter)
        finally:
            painter.end()
        return frame

    try:
        at_rest = paint(0.0)
        speaking = paint(1.0)
        mouth = face._portrait_bounds(240, 280, face._portrait.width(),
                                      face._portrait.height())
        center_x = round(mouth.left() + mouth.width() * 0.503)
        center_y = round(mouth.top() + mouth.height() * 0.605)
        # A changed pixel in the actual mouth area proves the portrait is
        # animated rather than displaying only the glowing status indicator.
        changes = sum(
            at_rest.pixel(x, y) != speaking.pixel(x, y)
            for y in range(center_y - 3, center_y + 9)
            for x in range(center_x - 15, center_x + 16)
        )
        assert changes > 10
        assert face._speech_mouth_opening(1.37, 0.0) == 0.0
        assert face._speech_mouth_opening(1.37, 1.0) > 0.0
        assert face._speech_mouth_opening(1.5, 1.0) != (
            face._speech_mouth_opening(1.37, 1.0)
        )
        face._speaking = 0.0
        assert paint(0.0) == at_rest
    finally:
        face.close()


@pytest.mark.unit
def test_portrait_speaking_animation_uses_real_shared_state(qapp, monkeypatch):
    """Qt's timer must react to the real shared SPEAKING state."""
    from types import SimpleNamespace
    from jarvis.activity import JarvisState
    from desktop_app.face_widget import FaceWidget

    face = FaceWidget()
    try:
        face._state_manager = SimpleNamespace(state=JarvisState.SPEAKING)
        face._last_frame_at -= 0.5
        face._animate()
        assert face._speaking > 0.8

        face._state_manager.state = JarvisState.IDLE
        face._last_frame_at -= 0.5
        face._animate()
        assert face._speaking < 0.2
    finally:
        face.close()


@pytest.mark.unit
def test_portrait_lips_follow_real_pcm_level_not_timer(qapp, monkeypatch):
    """An active Piper timeline must close on silence and open on voiced PCM."""
    from PyQt6.QtGui import QImage, QPainter
    import desktop_app.face_widget as face_module

    face = face_module.FaceWidget()
    face.resize(240, 280)
    from jarvis.activity import JarvisState
    face._speaking = 1.0
    face._jarvis_state = JarvisState.SPEAKING
    face._mouth_envelope = {"started_at": 123.0, "frame_ms": 40, "levels": [0, 100, 0]}

    def frame():
        canvas = QImage(240, 280, QImage.Format.Format_ARGB32_Premultiplied)
        canvas.fill(0)
        painter = QPainter(canvas)
        face._paint_portrait(painter)
        painter.end()
        return canvas

    try:
        monkeypatch.setattr(face_module, "envelope_level", lambda data: 0.0)
        silent_frame = frame()
        monkeypatch.setattr(face_module, "envelope_level", lambda data: 1.0)
        voiced_frame = frame()
        assert silent_frame != voiced_frame
        monkeypatch.setattr(face_module, "envelope_level", lambda data: 0.0)
        assert frame() == silent_frame
        face._jarvis_state = JarvisState.IDLE
        monkeypatch.setattr(face_module, "envelope_level", lambda data: 1.0)
        assert frame() == silent_frame  # no ghost articulation after playback
    finally:
        face.close()


@pytest.mark.unit
def test_live_atlas_holographic_mode_keeps_single_window_and_original_portrait(qapp):
    from desktop_app.face_widget import FaceWindow

    window = FaceWindow(hologram=True)
    try:
        assert window.windowTitle() == "🤖 ATLAS"
        assert window.face.parent() is window
        assert window.hologram.parent() is window
        assert window.bridge.parent() is window
        assert window.face.width() > 0
        assert window.hologram.width() > 0
        assert not window.face._portrait.isNull()
    finally:
        window.close()


@pytest.mark.unit
def test_explicit_legacy_vector_mode_does_not_replace_production_portrait(qapp):
    """Golden mask tests use vector fallback; the normal ATLAS portrait stays on."""
    from desktop_app.face_widget import FaceWindow, FaceWidget

    modern = FaceWindow()
    legacy = FaceWindow(portrait=False)
    try:
        assert not modern.face._portrait.isNull()
        assert legacy.face._portrait.isNull()
        assert legacy.width() == FaceWidget.DESIGN_WIDTH
        assert legacy.height() == FaceWidget.DESIGN_HEIGHT
        assert modern.windowTitle() == legacy.windowTitle() == "🤖 ATLAS"
    finally:
        legacy.close()
        modern.close()
