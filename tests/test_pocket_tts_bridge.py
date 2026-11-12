"""Pocket TTS opt-in integration without model downloads or real voice files."""

import io
import os
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from atlas.output.tts import PocketTTS, PiperTTS, SpeechRequest, create_tts_engine

pytestmark = pytest.mark.unit


def private_fixtures(tmp_path):
    binary = tmp_path / ("pocket-tts.exe" if os.name == "nt" else "pocket-tts")
    profile = tmp_path / "synthetic-voice.safetensors"
    binary.write_bytes(b"executable stub")
    profile.write_bytes(b"fake state, not a personal voice")
    return binary, profile


def test_default_voice_engine_stays_piper(tmp_path):
    binary, profile = private_fixtures(tmp_path)
    assert isinstance(create_tts_engine(enabled=False), PiperTTS)
    engine = create_tts_engine(
        engine="pocket", enabled=False,
        pocket_binary_path=str(binary), pocket_voice_profile=str(profile),
    )
    assert isinstance(engine, PocketTTS)
    assert engine.voice_profile == str(profile)


@pytest.mark.parametrize("case", ["missing", "relative", "not_state", "empty"])
def test_invalid_profile_is_refused_without_leaking_path(tmp_path, case):
    binary, profile = private_fixtures(tmp_path)
    if case == "missing":
        profile.unlink()
    elif case == "relative":
        profile = Path("synthetic-voice.safetensors")
    elif case == "not_state":
        profile = tmp_path / "synthetic-voice.wav"
        profile.write_bytes(b"test")
    else:
        profile.write_bytes(b"")
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    _, error = engine._prepare_speech()
    assert error and "Pocket TTS" in error
    assert "synthetic-voice" not in error


def test_startup_uses_french_loopback_private_state_and_offline(tmp_path, monkeypatch):
    import atlas.output.tts as speech
    binary, profile = private_fixtures(tmp_path)
    calls = []

    class Proc:
        def poll(self):
            return None
        def terminate(self):
            calls.append("terminated")
        def wait(self, timeout=None):
            return 0

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return Proc()

    class Session:
        trust_env = True
        def get(self, url, timeout):
            assert url.startswith("http://127.0.0.1:")
            return SimpleNamespace(
                status_code=200, json=lambda: {"status": "healthy"},
            )
        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        Session=Session, RequestException=OSError,
    ))
    monkeypatch.setattr(speech.subprocess, "Popen", fake_popen)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    assert engine._prepare_speech() == (True, None)
    argv, opts = calls[0]
    assert argv[:2] == [str(binary), "serve"]
    assert argv[argv.index("--language")+1] == "french"
    assert argv[argv.index("--host")+1] == "127.0.0.1"
    assert argv[argv.index("--default-voice")+1] == str(profile)
    assert opts["env"]["HF_HUB_OFFLINE"] == "1"
    assert opts["env"]["HF_ENDPOINT"] == "http://127.0.0.1:9"
    assert opts["stdout"] == speech.subprocess.DEVNULL
    engine._terminate_server()
    assert calls[-1] == "terminated"


def test_http_uses_only_text_and_cannot_upload_private_voice(tmp_path, monkeypatch):
    import requests
    binary, profile = private_fixtures(tmp_path)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    engine._port = 8765
    engine._server = SimpleNamespace(poll=lambda: None)
    calls = []

    class Response:
        status_code = 200
        headers = {"Content-Type": "audio/wav"}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def iter_content(self, chunk_size):
            yield b"RIFFdata"

    class Session:
        trust_env = True
        def post(self, url, data, stream, timeout):
            calls.append((url, data, stream, timeout, self.trust_env))
            return Response()
        def close(self):
            pass

    monkeypatch.setattr(requests, "Session", Session)
    assert engine._request_audio("Bonjour ATLAS") == b"RIFFdata"
    assert calls[0][0] == "http://127.0.0.1:8765/tts"
    assert calls[0][1] == {"text": "Bonjour ATLAS"}
    assert calls[0][-1] is False
    assert str(profile) not in str(calls)


def test_cancelled_transfer_never_returns_audio(tmp_path, monkeypatch):
    import requests
    binary, profile = private_fixtures(tmp_path)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    engine._port = 8765
    engine._server = SimpleNamespace(poll=lambda: None)

    class Response:
        status_code = 200
        headers = {"Content-Type": "audio/wav"}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def iter_content(self, chunk_size):
            engine._should_interrupt.set()
            yield b"RIFFdata"

    class Session:
        trust_env = True
        def post(self, *args, **kwargs):
            return Response()
        def close(self):
            pass

    monkeypatch.setattr(requests, "Session", Session)
    assert engine._request_audio("Bonjour ATLAS") is None


def test_real_wav_length_controls_playback_callbacks(tmp_path, monkeypatch):
    import atlas.output.lip_sync as sync
    binary, profile = private_fixtures(tmp_path)
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    wav_bytes = io.BytesIO()
    with wave.open(wav_bytes, "wb") as fp:
        fp.setnchannels(1)
        fp.setsampwidth(2)
        fp.setframerate(16000)
        fp.writeframes(b"\x00\x00" * 1600)
    monkeypatch.setattr(engine, "_request_audio", lambda text: wav_bytes.getvalue())
    played = []

    class Stream:
        def start(self):
            played.append("start")
        def write(self, samples):
            played.append(("pcm", len(samples)))
        def stop(self):
            played.append("stop")
        def close(self):
            played.append("close")
        def abort(self):
            played.append("abort")

    import sounddevice as sd
    monkeypatch.setattr(sd, "RawOutputStream", lambda **kwargs: Stream())
    monkeypatch.setattr(sync, "publish_envelope", lambda *a, **kw: None)
    monkeypatch.setattr(sync, "clear_envelope", lambda: None)
    durations = []
    monkeypatch.setattr(engine, "_begin_playback", lambda r, d: durations.append(d) or True)
    req = SpeechRequest("Bonjour", duration_callback=durations.append)
    assert engine._speak_once(req) is True
    assert durations == pytest.approx([0.1, 0.1])
    assert ("pcm", 2048) in played
    assert played[-1] == "close"


def test_unrelated_loopback_http_200_cannot_claim_pocket_ready(tmp_path, monkeypatch):
    """A wrong health payload is not proof that our child owns this port."""
    import atlas.output.tts as speech

    binary, profile = private_fixtures(tmp_path)
    calls = []
    class Process:
        def __init__(self):
            self.checks = 0
        def poll(self):
            self.checks += 1
            return None if self.checks == 1 else 1
        def terminate(self):
            calls.append("terminated")
        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(speech.subprocess, "Popen", lambda *a, **kw: Process())
    monkeypatch.setattr(speech.time, "sleep", lambda secs: None)

    class ForeignSession:
        trust_env = True
        def get(self, url, timeout):
            return SimpleNamespace(
                status_code=200, json=lambda: {"status": "unrelated"},
            )
        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        Session=ForeignSession, RequestException=OSError,
    ))
    engine = PocketTTS(binary_path=str(binary), voice_profile=str(profile))
    ready, explanation = engine._prepare_speech()
    assert ready is False
    assert explanation and "Pocket TTS" in explanation
    assert engine._server is None
