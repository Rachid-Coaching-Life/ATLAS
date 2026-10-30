"""Capture the real ATLAS Qt hologram offscreen, without starting the assistant.

Run from the repository root using:
    .\\.venv\\Scripts\\python.exe scripts\\preview_atlas_hologram_offscreen.py

The screenshot contains only the projection (never modifies the portrait).
No voice daemon, Ollama, model download, or system tray is launched.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Configure Qt *before* importing any Qt or desktop_app modules.
# This preview deliberately creates no native desktop window.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PyQt6.QtGui import QFont, QFontDatabase, QFontMetrics, QImage
from PyQt6.QtWidgets import QApplication

from desktop_app.hologram_panel import HologramPanel


def load_offscreen_font(app: QApplication) -> str:
    """Register real TTF fonts; offscreen Qt may not discover system fonts.

    Keep the font registration isolated to the preview. The interactive
    application retains its own native Windows font discovery and styling.
    """
    repo_root = Path(__file__).resolve().parent.parent
    candidates = []
    if os.name == "nt":
        windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates.extend([
            windows_fonts / "segoeui.ttf",
            windows_fonts / "segoeuib.ttf",
        ])
    # The existing font used by the icon generator provides an offline
    # fallback on non-Windows systems (no download or new dependency).
    candidates.append(
        repo_root / "src" / "desktop_app" / "desktop_assets"
        / "fonts" / "DejaVuSans.ttf"
    )

    families = []
    for path in candidates:
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    if not families:
        raise RuntimeError(
            "Aucune police TrueType chargeable pour le rendu Qt hors écran. "
            "Vérifier Windows\\Fonts et desktop_assets\\fonts."
        )
    family = families[0]
    font = QFont(family, 10)
    metrics = QFontMetrics(font)
    for character in "ATLASÀÉè«»":
        if not metrics.inFontUcs4(ord(character)):
            raise RuntimeError(
                f"La police {family!r} ne prend pas en charge {character!r}. "
                "Prévisualisation refusée pour éviter des carrés illisibles."
            )
    app.setFont(font)
    return family


def main() -> int:
    app = QApplication.instance() or QApplication([])
    loaded_family = load_offscreen_font(app)
    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.set_activity("idle")
        panel.set_voice_control(running=False)
        # These two labels specify Segoe UI explicitly in production. Force
        # the loaded family only for offscreen fallback font lookup.
        heading_font = panel.heading.font()
        heading_font.setFamily(loaded_family)
        panel.heading.setFont(heading_font)
        status_font = panel.status.font()
        status_font.setFamily(loaded_family)
        panel.status.setFont(status_font)
        panel.show()  # Offscreen Qt surface, no desktop window
        app.processEvents()

        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)

        destination = Path(tempfile.gettempdir()) / "ATLAS_hologram_preview.png"
        if not image.save(str(destination), "PNG"):
            raise RuntimeError("Impossible d'enregistrer la prévisualisation PNG")
        print(f"Police Qt hors écran : {loaded_family}")
        print(f"Prévisualisation ATLAS enregistrée : {destination}")
        return 0
    finally:
        panel.close()


if __name__ == "__main__":
    raise SystemExit(main())
