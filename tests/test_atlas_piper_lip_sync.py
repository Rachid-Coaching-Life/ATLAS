"""ATLAS lip motion follows the produced PCM energy, not a fake timer."""

import time

import numpy as np
import pytest

from jarvis.output import lip_sync

pytestmark = pytest.mark.unit


def test_pcm_envelope_opens_on_sound_and_closes_for_silence():
    rate = 16000
    audio = np.concatenate((
        np.zeros(rate // 5, dtype=np.int16),
        np.full(rate // 5, 12000, dtype=np.int16),
        np.zeros(rate // 5, dtype=np.int16),
    ))
    levels = lip_sync.make_envelope(audio, rate)
    assert len(levels) == 15
    assert max(levels[:5]) == 0
    assert min(levels[5:10]) > 60
    assert max(levels[10:]) == 0


def test_publish_and_read_exact_audio_time_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(lip_sync, "_ENVELOPE_FILE", tmp_path / "atlas.json")
    start = time.time() - .1
    lip_sync.publish_envelope([0, 40, 100, 0], start_time=start)
    data = lip_sync.read_envelope()
    assert data is not None
    assert data["frame_ms"] == 40
    assert lip_sync.envelope_level(data, now=start + .02) == 0
    assert lip_sync.envelope_level(data, now=start + .05) == .4
    assert lip_sync.envelope_level(data, now=start + .10) == 1
    assert lip_sync.envelope_level(data, now=start + .14) == 0
    assert lip_sync.envelope_level(data, now=start + .3) == 0
    lip_sync.clear_envelope()
    assert lip_sync.read_envelope() is None


def test_expired_or_invalid_envelopes_do_not_animate(tmp_path, monkeypatch):
    import json

    path = tmp_path / "atlas.json"
    monkeypatch.setattr(lip_sync, "_ENVELOPE_FILE", path)
    lip_sync.publish_envelope([100], start_time=time.time() - 600)
    assert lip_sync.read_envelope() is None

    path.write_text(json.dumps({
        "started_at": time.time(),
        "frame_ms": 40,
        "levels": [100, "bad", 0],
    }), encoding="utf-8")
    assert lip_sync.read_envelope() is None


def test_empty_signal_does_not_publish_or_open_mouth(tmp_path, monkeypatch):
    path = tmp_path / "atlas.json"
    monkeypatch.setattr(lip_sync, "_ENVELOPE_FILE", path)
    assert lip_sync.make_envelope(np.zeros(1600, dtype=np.int16), 16000) == [0, 0, 0]
    lip_sync.publish_envelope([])
    assert not path.exists()
