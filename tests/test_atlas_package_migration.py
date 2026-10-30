"""Structural safety checks for the ATLAS package migration planner."""
import importlib.util
from pathlib import Path


def _migration_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_atlas_package.py"
    spec = importlib.util.spec_from_file_location("atlas_package_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_imports_and_dynamic_patch_targets():
    tool = _migration_module()
    source = (
        "from jarvis.config import load_settings\n"
        "import jarvis\n"
        "from jarvis import activity\n"
        "patch('jarvis.listening.listener.sd')\n"
        "python -m jarvis.daemon\n"
    )
    result = tool.rewrite("src/desktop_app/app.py", source)
    assert "jarvis" not in result.lower()
    assert "from atlas.config import load_settings" in result
    assert "python -m atlas.daemon" in result


def test_configuration_keys_are_untouched():
    tool = _migration_module()
    sample = (
        'JARVIS_CONFIG_PATH = "test"\n'
        '"db_path": "~/.local/share/jarvis/jarvis.db"\n'
        'source_app="jarvis"\n'
    )
    assert tool.rewrite("src/atlas/config.py", sample) == sample


def test_build_manifest_bare_module():
    tool = _migration_module()
    assert tool.rewrite("atlas_desktop.spec", "'jarvis',\n'jarvis.main'") == "'atlas',\n'atlas.main'"
