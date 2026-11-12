"""Synthetic-only checks for the one-run private Windows voice bootstrap."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
from pathlib import Path
import sys
import zipfile

import pytest

pytestmark = pytest.mark.unit

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "atlas_voice_setup.py"
sys.path.insert(0, str(MODULE.parent))
spec = importlib.util.spec_from_file_location("atlas_voice_setup", MODULE)
setup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = setup
spec.loader.exec_module(setup)


def fake_release(exe=b"x" * 1_000_100):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as zf:
        zf.writestr("pocket-tts-3.3.0/pocket-tts.exe", exe)
    return result.getvalue()


class Download(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
        return False


def test_pinned_archive_extracts_expected_binary(tmp_path, monkeypatch):
    data = fake_release()
    monkeypatch.setattr(setup, "SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(sys.modules['prepare_pocket_voice'], 'EXPECTED_BINARY_SHA256',
                        hashlib.sha256(b'x' * 1_000_100).hexdigest())
    monkeypatch.setattr(setup, "urlopen", lambda *args, **kwargs: Download(data))
    monkeypatch.setattr(setup, "_binary_version", lambda _: setup.EXPECTED_BINARY_VERSION)
    binary = setup.install_official_binary(tmp_path)
    assert binary.read_bytes() == b"x" * 1_000_100
    assert not list(tmp_path.glob("*.zip"))
    assert list((tmp_path / "engine").iterdir()) == [binary]


def test_checksum_mismatch_never_publishes_binary(tmp_path, monkeypatch):
    data = fake_release()
    monkeypatch.setattr(setup, "SHA256", "0" * 64)
    monkeypatch.setattr(setup, "urlopen", lambda *args, **kwargs: Download(data))
    with pytest.raises(setup.SetupError, match="SHA-256"):
        setup.install_official_binary(tmp_path)
    assert not (tmp_path / "engine" / "pocket-tts.exe").exists()


def test_existing_wrong_binary_is_preserved(tmp_path, monkeypatch):
    binary = tmp_path / "engine" / "pocket-tts.exe"
    binary.parent.mkdir()
    binary.write_bytes(b"existing")
    monkeypatch.setattr(setup, "_binary_version", lambda _: "wrong")
    monkeypatch.setattr(setup, "urlopen", lambda *args, **kwargs: pytest.fail("download forbidden"))
    with pytest.raises(setup.SetupError, match="non conforme"):
        setup.install_official_binary(tmp_path)
    assert binary.read_bytes() == b"existing"


def test_private_reference_stays_local_and_temporary_token_cleared(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / setup.REFERENCE_NAME).write_bytes(b"synthetic audio placeholder")
    directory = tmp_path / "private"
    monkeypatch.setattr(setup, "private_dir", lambda: directory)
    monkeypatch.setattr(setup, "install_official_binary", lambda _: tmp_path / "pocket-tts.exe")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(setup, "_has_local_hf_auth", lambda: False)
    monkeypatch.setattr(setup, "_prompt_token", lambda: "hf_synthetic_not_a_real_token")
    seen = {}

    def fake_prepare(binary, reference, output, *, allow_download):
        seen.update(token=os.environ["HF_TOKEN"], reference=reference,
                    output=output, allowed=allow_download)

    monkeypatch.setattr(setup, "prepare", fake_prepare)
    setup.provision(bundle)
    assert seen["token"] == "hf_synthetic_not_a_real_token"
    assert seen["reference"] == bundle / setup.REFERENCE_NAME
    assert seen["output"] == directory / "voice_french.safetensors"
    assert seen["allowed"] is True
    assert "HF_TOKEN" not in os.environ


def test_existing_token_not_changed(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / setup.REFERENCE_NAME).write_bytes(b"synthetic placeholder")
    monkeypatch.setenv("HF_TOKEN", "hf_preexisting_test")
    monkeypatch.setattr(setup, "private_dir", lambda: tmp_path / "private")
    monkeypatch.setattr(setup, "install_official_binary", lambda _: tmp_path / "engine")
    monkeypatch.setattr(setup, "_prompt_token", lambda: pytest.fail("unwanted prompt"))
    monkeypatch.setattr(setup, "prepare", lambda *a, **kw: None)
    setup.provision(bundle)
    assert os.environ["HF_TOKEN"] == "hf_preexisting_test"


def test_existing_profile_is_not_replaced(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / setup.REFERENCE_NAME).write_bytes(b"synthetic placeholder")
    directory = tmp_path / "private"
    directory.mkdir()
    (directory / "voice_french.safetensors").write_bytes(b"old-profile")
    monkeypatch.setattr(setup, "private_dir", lambda: directory)
    monkeypatch.setattr(setup, "install_official_binary", lambda _: pytest.fail("no download"))
    with pytest.raises(setup.SetupError, match="existe déjà"):
        setup.provision(bundle)
    assert (directory / "voice_french.safetensors").read_bytes() == b"old-profile"


def test_failure_clears_temporary_token(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / setup.REFERENCE_NAME).write_bytes(b"synthetic placeholder")
    monkeypatch.setattr(setup, "private_dir", lambda: tmp_path / "private")
    monkeypatch.setattr(setup, "install_official_binary", lambda _: tmp_path / "engine")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(setup, "_has_local_hf_auth", lambda: False)
    monkeypatch.setattr(setup, "_prompt_token", lambda: "hf_synthetic")
    def fail(*args, **kwargs):
        raise setup.PreparationError("Synthetic failure")
    monkeypatch.setattr(setup, "prepare", fail)
    with pytest.raises(setup.SetupError, match="Synthetic failure"):
        setup.provision(bundle)
    assert "HF_TOKEN" not in os.environ


def test_requires_windows_localappdata(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(setup.SetupError, match="Windows"):
        setup.private_dir()


def test_unknown_existing_binary_is_never_executed(tmp_path, monkeypatch):
    binary = tmp_path / 'engine' / 'pocket-tts.exe'
    binary.parent.mkdir()
    binary.write_bytes(b'unknown executable')
    monkeypatch.setattr(setup, '_binary_version', lambda _: pytest.fail('unknown binary executed'))
    with pytest.raises(setup.SetupError, match='SHA-256'):
        setup.install_official_binary(tmp_path)
    assert binary.read_bytes() == b'unknown executable'


def test_failed_staged_execution_never_installs_binary(tmp_path, monkeypatch):
    data = fake_release()
    monkeypatch.setattr(setup, 'SHA256', hashlib.sha256(data).hexdigest())
    shared = sys.modules['prepare_pocket_voice']
    monkeypatch.setattr(shared, 'EXPECTED_BINARY_SHA256',
                        hashlib.sha256(b'x' * 1_000_100).hexdigest(), raising=False)
    monkeypatch.setattr(setup, 'urlopen', lambda *a, **kw: Download(data))
    def fail(binary):
        raise setup.SetupError('Synthetic execution failure')
    monkeypatch.setattr(setup, '_binary_version', fail)
    with pytest.raises(setup.SetupError, match='Synthetic execution failure'):
        setup.install_official_binary(tmp_path)
    assert not (tmp_path / 'engine' / 'pocket-tts.exe').exists()


def test_cached_verified_binary_is_reused_without_download(tmp_path, monkeypatch):
    binary = tmp_path / 'engine' / 'pocket-tts.exe'; binary.parent.mkdir()
    binary.write_bytes(b'trusted synthetic executable')
    monkeypatch.setattr(sys.modules['prepare_pocket_voice'], 'EXPECTED_BINARY_SHA256',
                        hashlib.sha256(binary.read_bytes()).hexdigest())
    monkeypatch.setattr(setup, '_binary_version', lambda _: setup.EXPECTED_BINARY_VERSION)
    monkeypatch.setattr(setup, 'urlopen', lambda *a, **kw: pytest.fail('unexpected download'))
    assert setup.install_official_binary(tmp_path) == binary


def test_installer_cleanup_preserves_primary_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup, 'urlopen', lambda *a, **kw: Download(fake_release()))
    monkeypatch.setattr(setup, 'SHA256', '0' * 64)
    unlink = Path.unlink
    def locked(path, *a, **kw):
        if path.suffix == '.zip':
            raise PermissionError('must not leak secret path')
        return unlink(path, *a, **kw)
    monkeypatch.setattr(Path, 'unlink', locked)
    with pytest.raises(setup.SetupError, match='SHA-256'):
        setup.install_official_binary(tmp_path)
    message = capsys.readouterr().err
    assert 'temporaires conservés' in message
    assert str(tmp_path) not in message
    assert 'secret path' not in message


def test_installer_refuses_redirected_ancestor_before_download(tmp_path, monkeypatch):
    real = tmp_path / 'real'; real.mkdir()
    alias = tmp_path / 'alias'
    if os.name == 'nt':
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(alias), str(real)],
                       check=True, capture_output=True)
    else:
        alias.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(setup, 'urlopen', lambda *a, **kw: pytest.fail('unexpected download'))
    try:
        with pytest.raises(setup.SetupError):
            setup.install_official_binary(alias / 'private')
        assert not list(real.iterdir())
    finally:
        alias.rmdir() if os.name == 'nt' else alias.unlink()


def test_bootstrap_io_error_is_sanitised(tmp_path, monkeypatch, capsys):
    def denied(root):
        raise PermissionError('do not print this sensitive path')
    monkeypatch.setattr(setup, 'provision', denied)
    assert setup.main(['--bundle-root', str(tmp_path)]) == 1
    error = capsys.readouterr().err
    assert 'Préparation interrompue' in error
    assert 'sensitive path' not in error
    assert str(tmp_path) not in error


@pytest.mark.skipif(os.name != 'nt', reason='Actual cmd.exe execution required')
@pytest.mark.parametrize('layout', ['scripts', 'flat'])
@pytest.mark.parametrize('exit_code', [0, 7])
@pytest.mark.parametrize('launcher_kind', ['python', 'py'])
def test_windows_cmd_launch_and_exit_code(tmp_path, layout, exit_code, launcher_kind):
    bundle = tmp_path / 'synthetic voice bundle'; bundle.mkdir()
    launcher = bundle / 'PREPARER_MA_VOIX_ATLAS.cmd'
    shutil.copyfile(MODULE.parent / launcher.name, launcher)
    scripts = bundle / 'scripts' if layout == 'scripts' else bundle
    scripts.mkdir(exist_ok=True)
    # Deliberately no model, reference, token or downloads: test the real CMD
    # boundary using a synthetic Python child with a known terminal outcome.
    (scripts / 'atlas_voice_setup.py').write_text(
        f'import sys\nprint("SYNTHETIC_CHILD", file=sys.stderr)\nsys.exit({exit_code})\n',
        encoding='utf-8',
    )
    env = os.environ.copy()
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + str(Path(env['SYSTEMROOT']) / 'System32')
    env['PYTHONUTF8'] = '1'
    if launcher_kind == 'python':
        assert shutil.which('py', path=env['PATH']) is None
    else:
        py = shutil.which('py')
        assert py, 'Native py launcher required to exercise py -3'
        env['PATH'] = str(Path(py).parent) + os.pathsep + env['PATH']
        assert shutil.which('py', path=env['PATH'])
    result = subprocess.run(['cmd.exe', '/d', '/c', str(launcher)], input='\n',
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=20, env=env)
    assert result.returncode == exit_code
    assert 'SYNTHETIC_CHILD' in result.stderr
    assert 'Appuyez sur une touche' in result.stdout


@pytest.mark.skipif(os.name != 'nt', reason='Actual cmd.exe execution required')
def test_windows_cmd_missing_script_reports_failure(tmp_path):
    launcher = tmp_path / 'PREPARER_MA_VOIX_ATLAS.cmd'
    shutil.copyfile(MODULE.parent / launcher.name, launcher)
    result = subprocess.run(['cmd.exe', '/d', '/c', str(launcher)], input='\n',
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=20)
    assert result.returncode == 1
    assert 'programme Python absent' in result.stdout
