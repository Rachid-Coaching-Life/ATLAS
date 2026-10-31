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


def test_windows_installer_build_names_without_touching_identity_or_data():
    tool = _migration_module()
    source = (
        '#define MyAppName "Jarvis"\n'
        '#define MyAppExeName "Jarvis.exe"\n'
        'OutputBaseFilename=Jarvis-Setup-x64\n'
        'Source: "..\\..\\dist\\Jarvis\\*"\n'
        'AppId={{B8A3D6F1-7C42-4E5A-9D12-3F8E6A1B5C90}\n'
    )
    result = tool.rewrite("installer/windows/jarvis_setup.iss", source)
    assert '#define MyAppName "ATLAS"' in result
    assert '#define MyAppExeName "ATLAS.exe"' in result
    assert 'OutputBaseFilename=ATLAS-Setup-x64' in result
    assert "dist\\ATLAS\\*" in result
    assert 'AppId={{B8A3D6F1-7C42-4E5A-9D12-3F8E6A1B5C90}' in result


def test_pyinstaller_executable_identity():
    tool = _migration_module()
    source = "name='Jarvis',\nname='Jarvis.app',\n'jarvis.daemon'"
    result = tool.rewrite("jarvis_desktop.spec", source)
    assert "name='ATLAS'," in result
    assert "name='ATLAS.app'," in result
    assert "'atlas.daemon'" in result


def test_windows_build_scripts_follow_renamed_manifest_and_binary():
    tool = _migration_module()
    source = (
        "pyinstaller jarvis_desktop.spec\n"
        "installer\\windows\\jarvis_setup.iss\n"
        "dist\\Jarvis\\Jarvis.exe\n"
        "dist\\Jarvis-Setup-x64.exe\n"
        "Jarvis-Windows-x64.zip\n"
    )
    for path in ("scripts/build_installer.bat", ".github/workflows/build-desktop.yml"):
        result = tool.rewrite(path, source)
        assert "atlas_desktop.spec" in result
        assert "atlas_setup.iss" in result
        assert "ATLAS.exe" in result
        assert "ATLAS-Setup-x64.exe" in result
        assert "ATLAS-Windows-x64.zip" in result
        assert "dist\\ATLAS\\ATLAS.exe" in result


def test_bundled_windows_smoke_uses_onedir_binary():
    tool = _migration_module()
    source = (
        "python -m PyInstaller jarvis_desktop.spec\n"
        "if exist \"dist\\Jarvis.exe\" (\n"
        "    dist\\Jarvis.exe\n"
        ")\n"
    )
    result = tool.rewrite("scripts/test_bundled_app.bat", source)
    assert "atlas_desktop.spec" in result
    assert 'if exist "dist\\ATLAS\\ATLAS.exe"' in result
    assert "    dist\\ATLAS\\ATLAS.exe" in result
