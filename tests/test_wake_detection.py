"""
Tests for wake word and stop command detection.
"""

import pytest

from jarvis.listening.wake_detection import (
    is_wake_word_detected,
    is_stop_command,
)


@pytest.mark.unit
class TestWakeWordDetection:
    """Tests for is_wake_word_detected."""

    def test_exact_match(self):
        assert is_wake_word_detected("hey jarvis", "jarvis", []) is True

    def test_alias_match(self):
        assert is_wake_word_detected("hey computer", "jarvis", ["computer"]) is True

    def test_no_match(self):
        assert is_wake_word_detected("hello world", "jarvis", []) is False

    def test_empty_text(self):
        assert is_wake_word_detected("", "jarvis", []) is False

    def test_fuzzy_match(self):
        """Fuzzy matching catches slight transcription errors."""
        assert is_wake_word_detected("hey jarvas", "jarvis", [], fuzzy_ratio=0.78) is True

    def test_fuzzy_below_threshold(self):
        """Completely different word doesn't fuzzy-match."""
        assert is_wake_word_detected("hey banana", "jarvis", [], fuzzy_ratio=0.78) is False


@pytest.mark.unit
class TestStopCommand:
    """Tests for is_stop_command."""

    def test_exact_stop_command(self):
        assert is_stop_command("stop", ["stop", "quiet"]) is True

    def test_stop_command_in_phrase(self):
        assert is_stop_command("please stop talking", ["stop", "quiet"]) is True

    def test_no_stop_command(self):
        assert is_stop_command("what is the weather", ["stop", "quiet"]) is False

    def test_empty_text(self):
        assert is_stop_command("", ["stop", "quiet"]) is False

    def test_fuzzy_stop_command(self):
        """Short input fuzzy-matches stop commands."""
        assert is_stop_command("stob", ["stop", "quiet"], fuzzy_ratio=0.7) is True



@pytest.mark.unit
class TestFrenchStopDefaults:
    """French interruption phrases work through the actual configured detector."""

    @pytest.mark.parametrize("heard", [
        "arrête", "Arrête !", "ARRE\u0302TE",
        "tais-toi", "TAIS TOI !", "Atlas, tais-toi !",
    ])
    def test_default_french_stop_interrupts(self, heard):
        from jarvis.config import get_default_config

        assert is_stop_command(
            heard, get_default_config()["stop_commands"],
        ), f"French stop should interrupt: {heard!r}"

    def test_french_stop_does_not_match_unrelated_infinitive(self):
        from jarvis.config import get_default_config

        assert not is_stop_command(
            "je voudrais arrêter la musique demain",
            get_default_config()["stop_commands"],
        )

    def test_loaded_settings_use_french_stop_defaults(self):
        from jarvis.config import load_settings

        assert is_stop_command("arrête !", load_settings().stop_commands)
        assert is_stop_command("tais-toi !", load_settings().stop_commands)

    @pytest.mark.parametrize("heard", ["arrête", "tais-toi"])
    def test_standalone_french_stop_is_not_discarded_as_tts_echo(self, heard):
        from jarvis.config import get_default_config
        from jarvis.listening.wake_detection import is_stop_command_echo

        # A standalone interruption control retains priority over playback echo.
        assert not is_stop_command_echo(
            heard, heard, get_default_config()["stop_commands"],
        )

    @pytest.mark.parametrize("custom", [["pause"], []])
    def test_explicit_custom_stop_settings_remain_authoritative(
        self, custom, monkeypatch, tmp_path,
    ):
        import json
        from jarvis.config import load_settings

        config = tmp_path / "atlas-config.json"
        config.write_text(
            json.dumps({"_config_version": 3, "stop_commands": custom}),
            encoding="utf-8",
        )
        monkeypatch.setenv("JARVIS_CONFIG_PATH", str(config))
        loaded = load_settings().stop_commands

        assert loaded == custom
        assert not is_stop_command("arrête", loaded)


@pytest.mark.unit
@pytest.mark.parametrize(("heard", "expected"), [
    ("ATLAS", True),
    ("Atlas.", True),
    ("atlas ?", True),
    ("Atlasse!", True),
    ("Atlas, ouvre le dossier", False),
    ("Un atlas géographique", False),
    ("Atlassement", False),
    ("Atla", False),
    ("", False),
])
def test_exact_standalone_wake_name_only(heard, expected):
    from jarvis.listening.wake_detection import is_standalone_wake_word
    assert is_standalone_wake_word(heard, "atlas", ["atlasse"]) is expected


@pytest.mark.unit
@pytest.mark.parametrize(("heard", "expected"), [
    ("Atlas, ouvre mon dossier", True),
    ("ATLAS, présente-toi en français", True),
    ("Atlasse, explique le problème", True),
    ("atlas, peux-tu m'aider ?", True),
    ("Atlas: ouvre mon dossier", False),
    ("Atlas ouvre mon dossier", False),
    ("Atlas,", False),
    ("Atlas", False),
    ("Un atlas géographique, ouvre un livre", False),
    ("Je parle à Atlas, ouvre mon dossier", False),
    ('"Atlas, ouvre mon dossier"', False),
    ("Atlassement, ouvre mon dossier", False),
    ("Atla, ouvre mon dossier", False),
    ("", False),
])
def test_explicit_wake_address_requires_literal_initial_name_and_comma(heard, expected):
    """Only a clear direct address may bypass the slower LLM intent judge."""
    from jarvis.listening.wake_detection import is_explicit_wake_address

    assert is_explicit_wake_address(heard, "atlas", ["atlasse"]) is expected
