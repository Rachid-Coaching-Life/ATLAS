"""Local voice-reference admission. Never use personal recordings in CI."""

from __future__ import annotations

import sys
import wave
from types import ModuleType, SimpleNamespace

import pytest

from atlas.output.tts import (
    ChatterboxTTS, PiperTTS, SpeechRequest, create_tts_engine,
)

pytestmark = pytest.mark.unit


def _synthetic_wav(tmp_path):
    path = tmp_path / "local-reference.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00" * 3200)
    return path


def test_valid_reference_is_admitted_without_model_load(tmp_path, monkeypatch):
    wav = _synthetic_wav(tmp_path)
    tts = create_tts_engine(
        engine="chatterbox", enabled=True, audio_prompt_path=str(wav),
    )
    assert isinstance(tts, ChatterboxTTS)
    calls = []
    monkeypatch.setattr(tts, "_ensure_model", lambda: calls.append(True) or True)
    assert tts._prepare_speech() == (True, None)
    assert calls == [True]
    assert tts.audio_prompt_path == str(wav)


@pytest.mark.parametrize("invalid", ["missing", "relative", "extension", "header"])
def test_invalid_private_reference_fails_before_model_load(
    tmp_path, monkeypatch, invalid,
):
    path = tmp_path / "secret-private-voice.wav"
    if invalid == "relative":
        candidate = "secret-private-voice.wav"
    elif invalid == "extension":
        path = tmp_path / "secret-private-voice.txt"
        path.write_bytes(b"not a wave")
        candidate = str(path)
    elif invalid == "header":
        path.write_bytes(b"not a wave")
        candidate = str(path)
    else:
        candidate = str(path)
    tts = ChatterboxTTS(enabled=True, audio_prompt_path=candidate)
    monkeypatch.setattr(
        tts, "_ensure_model",
        lambda: pytest.fail("Invalid reference must not load the model"),
    )
    available, explanation = tts._prepare_speech()
    assert available is False
    assert explanation and "Référence vocale" in explanation
    assert "secret-private-voice" not in explanation


def test_stub_model_receives_configured_reference_before_playback(
    tmp_path, monkeypatch,
):
    """Stop at generate(), before audio output, after observing its arguments."""
    wav = _synthetic_wav(tmp_path)
    tts = ChatterboxTTS(enabled=True, audio_prompt_path=str(wav))
    calls = []

    class SimulatedStop(Exception):
        pass

    def generate(text, **kwargs):
        calls.append((text, kwargs))
        raise SimulatedStop("simulated generation failure")

    monkeypatch.setattr(tts, "_ensure_model", lambda: True)
    tts._model = SimpleNamespace(generate=generate, sr=16000)
    monkeypatch.setitem(sys.modules, "pygame", ModuleType("pygame"))
    with pytest.warns(UserWarning, match="Chatterbox TTS error"):
        assert tts._speak_once(SpeechRequest("Bonjour ATLAS")) is False
    assert len(calls) == 1
    spoken, kwargs = calls[0]
    assert spoken == "Bonjour ATLAS"
    assert kwargs["audio_prompt_path"] == str(wav)
    assert kwargs["exaggeration"] == tts.exaggeration
    assert kwargs["cfg_weight"] == tts.cfg_weight


def test_default_piper_selection_is_unchanged():
    assert isinstance(create_tts_engine(enabled=False), PiperTTS)
