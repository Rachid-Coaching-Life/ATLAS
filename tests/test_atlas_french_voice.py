"""Regression contracts for ATLAS's French voice path (offline-only tests)."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_network")]


def test_unconfigured_piper_downloads_french_voice(monkeypatch, tmp_path):
    """An existing null tts_piper_model_path must select French, not English."""
    from jarvis.output import tts as speech

    monkeypatch.setattr(speech, "_get_piper_models_dir", lambda: tmp_path)
    requested_voices = []

    def unavailable_download(voice_name, progress_callback=None):
        requested_voices.append(voice_name)
        return None

    with patch.object(speech, "_download_piper_voice", side_effect=unavailable_download):
        instance = speech.PiperTTS(enabled=True)
        assert instance._ensure_initialized() is False

    assert requested_voices == ["fr_FR-tom-medium"]


def test_configured_piper_model_stays_prioritary(monkeypatch, tmp_path):
    """Personal voice selection must not be overridden by the new default."""
    from jarvis.output import tts as speech

    monkeypatch.setattr(speech, "_get_piper_models_dir", lambda: tmp_path)
    requested_voices = []

    def unavailable_download(voice_name, progress_callback=None):
        requested_voices.append(voice_name)
        return None

    custom = tmp_path / "fr_FR-siwis-medium.onnx"
    with patch.object(speech, "_download_piper_voice", side_effect=unavailable_download):
        instance = speech.PiperTTS(enabled=True, model_path=str(custom))
        assert instance._ensure_initialized() is False

    assert requested_voices == ["fr_FR-siwis-medium"]


def test_french_piper_catalog_paths(monkeypatch, tmp_path):
    """French model and metadata use the exact official Piper v1.0.0 paths."""
    from jarvis.output import tts as speech

    monkeypatch.setattr(speech, "_get_piper_models_dir", lambda: tmp_path)
    downloaded = []

    def download_locally(url, target_path, *args):
        downloaded.append(url)
        target_path.write_bytes(b"synthetic-model" if url.endswith(".onnx") else b"{}")

    with patch.object(speech, "_download_piper_file", side_effect=download_locally):
        chosen = speech._download_piper_voice("fr_FR-tom-medium")

    assert chosen == str(tmp_path / "fr_FR-tom-medium.onnx")
    assert downloaded == [
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
        "fr/fr_FR/tom/medium/fr_FR-tom-medium.onnx",
        "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
        "fr/fr_FR/tom/medium/fr_FR-tom-medium.onnx.json",
    ]


def test_active_tts_never_inserts_english_only_instruction(
    mock_config, db, dialogue_memory, monkeypatch,
):
    """The alternate direct-TTS reply path must honour French-only persona."""
    from jarvis.reply import engine

    monkeypatch.setattr(engine, "plan_query", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        engine, "select_tools", lambda **kwargs: list(kwargs["builtin_tools"])
    )
    system_messages = []

    def local_model(*args, **kwargs):
        messages = kwargs["messages"]
        system_messages.extend(
            message["content"] for message in messages if message["role"] == "system"
        )
        return {"message": {"content": "Bonjour.", "role": "assistant"}}

    simulated_speech = SimpleNamespace(
        enabled=True, speak=lambda *args, **kwargs: None,
    )
    with patch.object(engine, "chat_with_messages", side_effect=local_model), \
         patch.object(
             engine, "extract_search_params_for_memory", return_value={"keywords": []},
         ):
        reply = engine.run_reply_engine(
            db=db,
            cfg=mock_config,
            tts=simulated_speech,
            text="Bonjour, Atlas",
            dialogue_memory=dialogue_memory,
        )

    assert reply == "Bonjour."
    assert system_messages
    assert all("Always answer in French" in prompt for prompt in system_messages)
    assert all("Always respond in English" not in prompt for prompt in system_messages)
