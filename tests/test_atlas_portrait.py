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
        assert window.width() == 280
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
