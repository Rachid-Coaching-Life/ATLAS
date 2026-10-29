"""Tiny cross-process Piper amplitude timeline for ATLAS's desktop portrait.

The entire timeline is published once before playback. PortAudio callbacks do
not perform file I/O, locks or GUI work. This carries acoustic energy, not
phoneme alignment; it can animate mouth opening but not accurate visemes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time


_ENVELOPE_FILE = Path(tempfile.gettempdir()) / "atlas_piper_mouth.json"
_FRAME_MS = 40


def make_envelope(audio, sample_rate: int) -> list[int]:
    """Return quantised relative RMS energy per 40ms of existing int16 audio."""
    if sample_rate <= 0 or len(audio) == 0:
        return []
    import numpy as np

    frame_samples = max(1, round(sample_rate * _FRAME_MS / 1000))
    rms = []
    for start in range(0, len(audio), frame_samples):
        block = np.asarray(audio[start:start + frame_samples], dtype=np.float32)
        rms.append(float(np.sqrt(np.mean(block * block))) / 32768.0)
    peak = max(rms, default=0.0)
    if peak < 0.001:
        return [0] * len(rms)
    # Relative to this utterance: quiet phonemes open less than voiced peaks.
    threshold = peak * 0.11
    scale = peak * 0.62
    return [
        min(100, max(0, round(100 * (level - threshold) / scale)))
        for level in rms
    ]


def publish_envelope(levels: list[int], *, start_time: float | None = None) -> None:
    """Atomically publish playback energy with wall-clock alignment."""
    if not levels:
        return
    payload = {
        "started_at": time.time() if start_time is None else start_time,
        "frame_ms": _FRAME_MS,
        "levels": levels,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=_ENVELOPE_FILE.parent,
            prefix=".atlas-mouth-", suffix=".tmp", delete=False,
        ) as fp:
            temporary = fp.name
            json.dump(payload, fp, separators=(",", ":"))
        os.replace(temporary, _ENVELOPE_FILE)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def read_envelope() -> dict | None:
    """Read a recent envelope without depending on the TTS process."""
    try:
        data = json.loads(_ENVELOPE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        start = float(data["started_at"])
        frame_ms = int(data["frame_ms"])
        levels = data["levels"]
        if not isinstance(levels, list) or not (10 <= frame_ms <= 100):
            return None
        if not levels or len(levels) > 30000:
            return None
        if not 0 <= time.time() - start <= max(30, len(levels) * frame_ms / 1000 + 2):
            return None
        if any(type(v) is not int or v < 0 or v > 100 for v in levels):
            return None
        return {"started_at": start, "frame_ms": frame_ms, "levels": levels}
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def envelope_level(data: dict, *, now: float | None = None) -> float:
    """Find the mouth opening for the currently audible 40ms block."""
    if now is None:
        now = time.time()
    index = int((now - data["started_at"]) * 1000 / data["frame_ms"])
    levels = data["levels"]
    if index < 0 or index >= len(levels):
        return 0.0
    return float(levels[index]) / 100.0


def clear_envelope() -> None:
    """Best-effort cleanup after Piper playback, including interruption."""
    try:
        _ENVELOPE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
