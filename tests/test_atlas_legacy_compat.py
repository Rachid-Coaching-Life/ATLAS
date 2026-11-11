"""Legacy compatibility: environment aliases and non-destructive data migration."""
import json

import pytest

from atlas import legacy_compat

pytestmark = pytest.mark.unit


def test_old_variable_becomes_an_alias():
    env = {"JARVIS_VOICE_DEBUG": "1"}
    assert legacy_compat.apply_env_aliases(env) == ["ATLAS_VOICE_DEBUG"]
    assert env["ATLAS_VOICE_DEBUG"] == "1"
    assert env["JARVIS_VOICE_DEBUG"] == "1"


def test_new_variable_always_wins():
    env = {"JARVIS_X": "old", "ATLAS_X": "new"}
    assert legacy_compat.apply_env_aliases(env) == []
    assert env["ATLAS_X"] == "new"


def test_unrelated_variables_are_left_alone():
    env = {"PATH": "/bin", "OTHER_JARVIS_X": "1"}
    assert legacy_compat.apply_env_aliases(env) == []
    assert env == {"PATH": "/bin", "OTHER_JARVIS_X": "1"}


def make_legacy_home(tmp_path):
    home = tmp_path / "home"
    old = home / ".config" / "jarvis"
    (old / "sub").mkdir(parents=True)
    (old / "config.json").write_text(json.dumps({"jarvis_name": "x", "keep": {"jarvis_deep": 1}}))
    (old / "jarvis.db").write_bytes(b"data")
    (old / "sub" / "note.txt").write_text("hello")
    return home, old


def test_data_is_copied_not_moved(tmp_path):
    home, old = make_legacy_home(tmp_path)
    created = legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True)
    new = home / ".config" / "atlas"
    assert created == [new]
    assert (new / "atlas.db").read_bytes() == b"data"
    assert (new / "sub" / "note.txt").read_text() == "hello"
    assert (new / legacy_compat.MARKER).is_file()
    assert (old / "jarvis.db").read_bytes() == b"data"
    assert json.loads((old / "config.json").read_text())["jarvis_name"] == "x"


def test_config_keys_are_renamed_but_not_values(tmp_path):
    home, _ = make_legacy_home(tmp_path)
    legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True)
    data = json.loads((home / ".config" / "atlas" / "config.json").read_text())
    assert data == {"atlas_name": "x", "keep": {"atlas_deep": 1}}


def test_existing_new_directory_is_never_touched(tmp_path):
    home, _ = make_legacy_home(tmp_path)
    new = home / ".config" / "atlas"
    new.mkdir(parents=True)
    (new / "mine.txt").write_text("keep")
    assert legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True) == []
    assert sorted(path.name for path in new.iterdir()) == ["mine.txt"]


def test_second_run_does_nothing(tmp_path):
    home, _ = make_legacy_home(tmp_path)
    assert legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True)
    assert legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True) == []


def test_skipped_under_pytest_and_by_variable(tmp_path):
    home, _ = make_legacy_home(tmp_path)
    assert legacy_compat.migrate_user_data(home=home, environ={}, platform="linux") == []
    assert legacy_compat.migrate_user_data(
        home=home, environ={legacy_compat.SKIP_VARIABLE: "1"}, platform="linux", force=False) == []
    assert not (home / ".config" / "atlas").exists()


def test_home_dot_directory_is_found(tmp_path):
    home = tmp_path / "home"
    (home / ".jarvis").mkdir(parents=True)
    (home / ".jarvis" / "state.json").write_text("{}")
    assert legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True) == [home / ".atlas"]
    assert (home / ".atlas" / "state.json").is_file()
    assert (home / ".jarvis" / "state.json").is_file()


def test_failure_never_raises(tmp_path, monkeypatch):
    home, _ = make_legacy_home(tmp_path)

    def broken(old, new):
        raise OSError("disk full")

    monkeypatch.setattr(legacy_compat, "_copy_renamed", broken)
    assert legacy_compat.migrate_user_data(home=home, environ={}, platform="linux", force=True) == []
    assert (home / ".config" / "jarvis" / "jarvis.db").is_file()
