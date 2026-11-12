"""Synthetic-only checks for the one-run private Windows voice bootstrap."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
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
    monkeypatch.setattr(setup, "urlopen", lambda *args, **kwargs: Download(data))
    monkeypatch.setattr(setup, "_binary_version", lambda _: setup.EXPECTED_BINARY_VERSION)
    binary = setup.install_official_binary(tmp_path)
    assert binary.read_bytes() == b"x" * 1_000_100
    assert not list(tmp_path.glob("*.zip"))
    assert not list((tmp_path / "engine").glob("*.tmp"))


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
