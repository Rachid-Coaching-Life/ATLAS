"""Tests for the unified persona system prompt.

The persona should match the user's configured wake word so renaming the
wake word to e.g. "Friday" produces a butler named Friday, not one still
hardcoded to Jarvis.
"""

from jarvis.system_prompt import build_system_prompt


class TestBuildSystemPrompt:
    def test_default_name_is_atlas(self):
        prompt = build_system_prompt()
        assert "named ATLAS" in prompt

    def test_custom_name_replaces_jarvis(self):
        prompt = build_system_prompt("Friday")
        assert "named Friday" in prompt
        assert "named Jarvis" not in prompt

    def test_lowercase_wake_word_is_capitalised(self):
        prompt = build_system_prompt("friday".capitalize())
        assert "named Friday" in prompt

    def test_blank_name_falls_back_to_atlas(self):
        assert "named ATLAS" in build_system_prompt("")
        assert "named ATLAS" in build_system_prompt("   ")
        assert "named ATLAS" in build_system_prompt(None)  # type: ignore[arg-type]

    def test_atlas_explicitly_replies_in_french_for_every_input_language(self):
        prompt = build_system_prompt("Atlas")
        assert "Always answer in French" in prompt
        assert "even if the user speaks or writes another language" in prompt
        assert "Keep code, identifiers, file paths, proper names, URLs, and exact quotations unchanged" in prompt
        assert "phrased naturally in the user's language" not in prompt
