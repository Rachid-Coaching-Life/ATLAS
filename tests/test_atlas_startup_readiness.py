"""ATLAS announces microphone readiness without transcribing its own greeting."""

from unittest.mock import MagicMock, patch

import pytest

from test_hot_window_input import _create_listener

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_network")]


def test_ready_greeting_holds_capture_until_tts_completes(capsys):
    listener, tts = _create_listener()
    try:
        listener._announce_voice_ready()

        tts.speak.assert_called_once()
        args, kwargs = tts.speak.call_args
        assert args == ("Je suis ATLAS, à votre service.",)
        assert listener.capture_paused
        assert listener.is_capture_paused("startup_greeting")
        assert "écoute active" not in capsys.readouterr().out

        kwargs["terminal_callback"]("completed")

        assert not listener.capture_paused
        assert not listener.is_capture_paused("startup_greeting")
        assert "ATLAS prêt : écoute active" in capsys.readouterr().out
    finally:
        listener.stop()


@pytest.mark.parametrize("outcome", ["failed", "cancelled", "interrupted", "rejected"])
def test_ready_greeting_releases_microphone_even_if_tts_fails(outcome, capsys):
    listener, tts = _create_listener()
    try:
        listener._announce_voice_ready()
        assert listener.capture_paused

        tts.speak.call_args.kwargs["terminal_callback"](outcome)

        assert not listener.capture_paused
        assert "écoute active" in capsys.readouterr().out
    finally:
        listener.stop()


def test_no_voice_backend_still_reports_listening(capsys):
    listener, tts = _create_listener()
    try:
        tts.enabled = False
        listener._announce_voice_ready()
        tts.speak.assert_not_called()
        assert not listener.capture_paused
        assert "écoute active" in capsys.readouterr().out
    finally:
        listener.stop()


def test_greeting_exception_does_not_leave_capture_paused(capsys):
    listener, tts = _create_listener()
    try:
        tts.speak.side_effect = RuntimeError("device unavailable")
        listener._announce_voice_ready()
        assert not listener.capture_paused
        assert "écoute active" in capsys.readouterr().out
    finally:
        listener.stop()


def test_other_capture_pause_is_not_cleared_by_greeting_completion(capsys):
    listener, tts = _create_listener()
    try:
        listener._announce_voice_ready()
        listener.set_capture_paused("dictation", True)
        tts.speak.call_args.kwargs["terminal_callback"]("completed")

        assert listener.capture_paused
        assert not listener.is_capture_paused("startup_greeting")
        assert listener.is_capture_paused("dictation")
        assert "écoute temporairement suspendue" in capsys.readouterr().out
    finally:
        listener.stop()


def test_stop_before_greeting_skips_speech(capsys):
    listener, tts = _create_listener()
    listener.stop()
    listener._announce_voice_ready()
    tts.speak.assert_not_called()
    assert not listener.capture_paused
    assert not capsys.readouterr().out
