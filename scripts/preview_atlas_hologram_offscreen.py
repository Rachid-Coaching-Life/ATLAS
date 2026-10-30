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

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from desktop_app.hologram_panel import HologramPanel


def main() -> int:
    app = QApplication.instance() or QApplication([])
    panel = HologramPanel()
    try:
        panel.resize(505, 330)
        panel.set_activity("idle")
        panel.set_voice_control(running=False)
        panel.show()  # Offscreen Qt surface, no desktop window
        app.processEvents()

        image = QImage(panel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        panel.render(image)

        destination = Path(tempfile.gettempdir()) / "ATLAS_hologram_preview.png"
        if not image.save(str(destination), "PNG"):
            raise RuntimeError("Impossible d'enregistrer la prévisualisation PNG")
        print(f"Prévisualisation ATLAS enregistrée : {destination}")
        return 0
    finally:
        panel.close()


if __name__ == "__main__":
    raise SystemExit(main())
