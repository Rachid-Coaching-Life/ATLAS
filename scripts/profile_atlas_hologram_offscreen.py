"""Measure ATLAS Qt raster-paint cost offscreen, with no voice daemon or desktop.

Run from repository root:
    .\\.venv\\Scripts\\python.exe scripts\\profile_atlas_hologram_offscreen.py

This measures QWidget.render(QImage) times, *not* GPU, Windows desktop
compositing, system wattage or resistance to abrupt power loss.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
import time
from pathlib import Path

# Must be set before *any* PyQt/desktop_app import: no native desktop window.
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from preview_atlas_hologram_offscreen import load_offscreen_font
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
from desktop_app.face_widget import FaceWidget
from desktop_app.hologram_panel import HologramPanel, ProjectionBridge


def measure(widget, *, warmup: int, samples: int) -> dict:
    """Time raster paint only. Allocate and clear the QImage outside the clock."""
    if widget.width() <= 0 or widget.height() <= 0:
        raise ValueError("Dimensions du composant invalides")
    frame = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    if frame.isNull():
        raise RuntimeError("Impossible d'allouer le buffer QImage")

    values_ms = []
    for number in range(warmup + samples):
        frame.fill(0)
        begin = time.perf_counter_ns()
        widget.render(frame)
        elapsed_ms = (time.perf_counter_ns() - begin) / 1_000_000
        if number >= warmup:
            values_ms.append(elapsed_ms)

    values_ms.sort()
    p95 = values_ms[max(0, int((len(values_ms) - 1) * .95))]
    return {
        "width": widget.width(),
        "height": widget.height(),
        "median_ms": round(statistics.median(values_ms), 3),
        "mean_ms": round(statistics.mean(values_ms), 3),
        "p95_ms": round(p95, 3),
        "min_ms": round(values_ms[0], 3),
        "max_ms": round(values_ms[-1], 3),
    }


def profile(*, samples: int, warmup: int) -> dict:
    app = QApplication.instance() or QApplication([])
    font_name = load_offscreen_font(app)
    results = {}
    initial = os.environ.get("ATLAS_HOLOGRAM_LOW_EFFECTS")
    initial_cache = os.environ.get("ATLAS_HOLOGRAM_CACHED_EFFECTS")
    try:
        for mode in ("normal", "alleger", "hybride"):
            os.environ["ATLAS_HOLOGRAM_LOW_EFFECTS"] = "0" if mode == "normal" else "1"
            os.environ["ATLAS_HOLOGRAM_CACHED_EFFECTS"] = "1" if mode == "hybride" else "0"
            for state in ("idle", "listening"):
                panel = HologramPanel()
                bridge = ProjectionBridge()
                try:
                    panel.resize(505, 330)
                    bridge.setFixedSize(47, 330)
                    panel.set_activity(state)
                    bridge.set_activity(state)
                    panel.show()
                    bridge.show()
                    app.processEvents()
                    key = mode + "_" + state
                    results["hologram_" + key] = measure(
                        panel, warmup=warmup, samples=samples
                    )
                    results["bridge_" + key] = measure(
                        bridge, warmup=warmup, samples=samples
                    )
                    results["hologram_" + key]["timer_ms"] = panel._timer.interval()
                    results["bridge_" + key]["timer_ms"] = bridge._timer.interval()
                finally:
                    panel.close()
                    bridge.close()
        # The face portrait itself is never changed. This is the existing Qt
        # renderer, measured separately rather than attributed to the HUD.
        face = FaceWidget()
        try:
            if face._portrait.isNull():
                raise RuntimeError("Le portrait ATLAS est introuvable")
            face.resize(274, 330)
            face.show()
            app.processEvents()
            results["portrait_idle"] = measure(face, warmup=warmup, samples=samples)
            # Voice/speaking paint cost only; do not start an audio daemon.
            from jarvis.activity import JarvisState
            face._jarvis_state = JarvisState.SPEAKING
            face._speaking = 1.0
            face._elapsed = 1.3
            results["portrait_speaking"] = measure(face, warmup=warmup, samples=samples)
        finally:
            face.close()
    finally:
        if initial is None:
            os.environ.pop("ATLAS_HOLOGRAM_LOW_EFFECTS", None)
        else:
            os.environ["ATLAS_HOLOGRAM_LOW_EFFECTS"] = initial
        if initial_cache is None:
            os.environ.pop("ATLAS_HOLOGRAM_CACHED_EFFECTS", None)
        else:
            os.environ["ATLAS_HOLOGRAM_CACHED_EFFECTS"] = initial_cache

    return {
        "tool": "ATLAS Qt offscreen raster profiler",
        "platform": os.environ["QT_QPA_PLATFORM"],
        "font": font_name,
        "samples": samples,
        "warmup": warmup,
        "unit": "millisecondes par rendu QWidget.render(QImage)",
        "not_measured": [
            "Puissance du chargeur USB-C, watts de la machine",
            "GPU et composition DWM Windows",
            "Fréquence effective des images de la fenêtre native",
            "Stabilité face aux extinctions matérielles",
        ],
        "measurements": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=4)
    parser.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()) / "ATLAS_offscreen_render_profile.json")
    args = parser.parse_args()
    if not 1 <= args.samples <= 120 or not 0 <= args.warmup <= 20:
        parser.error("samples: 1-120, warmup: 0-20")
    result = profile(samples=args.samples, warmup=args.warmup)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("ATLAS — mesure du rendu Qt hors écran (pas une mesure GPU)")
    print(f"Police : {result['font']}  |  échantillons : {args.samples}")
    for name, row in result["measurements"].items():
        print(f"  {name:30s} médiane={row['median_ms']:8.3f} ms  p95={row['p95_ms']:8.3f} ms")
    print(f"Rapport JSON : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
