"""Guard against destructive Windows installer behavior in ATLAS."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

INSTALLER = Path(__file__).resolve().parents[1] / "installer" / "windows" / "atlas_setup.iss"


def _installer_text() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_installer_keeps_downloaded_setup_and_user_files():
    script = _installer_text()
    # Inno Setup records the files it installs and removes them on uninstall.
    # An unconditional wildcard removal of {app} may delete files ATLAS did
    # not install; deleting {srcexe} would erase a user's downloaded installer.
    assert "[UninstallDelete]" not in script
    assert "procedure DeinitializeSetup" not in script
    assert "del /f" not in script.lower()
    assert "deletefile(" not in script.lower()


def test_installer_uses_atlas_identity_and_bundled_executable():
    script = _installer_text()
    assert '#define MyAppName "ATLAS"' in script
    assert '#define MyAppExeName "ATLAS.exe"' in script
    assert 'OutputBaseFilename=ATLAS-Setup-x64' in script
    assert r'Source: "..\..\dist\ATLAS\*"' in script
    assert r'Filename: "{app}\{#MyAppExeName}"' in script
