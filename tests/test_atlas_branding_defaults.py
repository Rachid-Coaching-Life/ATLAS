"""ATLAS identity defaults never silently discard an existing Jarvis configuration."""

import json

import pytest

from jarvis.config import get_default_config, load_settings
from jarvis.system_prompt import build_system_prompt


@pytest.mark.unit
def test_new_install_uses_atlas_name_and_french_alias():
    defaults = get_default_config()
    assert defaults["wake_word"] == "atlas"
    assert defaults["wake_aliases"] == ["atlasse"]
    assert "named ATLAS" in build_system_prompt()


@pytest.mark.unit
def test_existing_saved_wake_word_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "personal-settings.json"
    path.write_text(json.dumps({
        "_config_version": 3,
        "wake_word": "jarvis",
        "wake_aliases": ["jaivis"],
    }), encoding="utf-8")
    monkeypatch.setenv("JARVIS_CONFIG_PATH", str(path))

    loaded = load_settings()

    assert loaded.wake_word == "jarvis"
    assert loaded.wake_aliases == ["jaivis"]
    assert json.loads(path.read_text(encoding="utf-8"))["wake_word"] == "jarvis"
