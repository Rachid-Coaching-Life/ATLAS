"""Synthetic only: no voice recording, Hugging Face credentials or real model."""
from __future__ import annotations

import importlib.util
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit
MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'prepare_pocket_voice.py'
spec = importlib.util.spec_from_file_location('atlas_private_pocket_prep', MODULE)
prep = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prep
spec.loader.exec_module(prep)


def synthetic_wav(path, *, duration=5, amplitude=1200):
    with wave.open(str(path), 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes((amplitude.to_bytes(2, 'little', signed=True)) * (16000 * duration))


def fake_output_wav(path):
    synthetic_wav(path, duration=1)


def test_prepare_offline_exports_private_state_without_overwriting(tmp_path, monkeypatch):
    binary = tmp_path / 'pocket-tts.exe'
    binary.write_bytes(b'test')
    reference = tmp_path / 'synthetic.wav'
    synthetic_wav(reference)
    output = tmp_path / 'private' / 'voice.safetensors'
    commands = []
    def fake_run(args, **kwargs):
        commands.append((args, kwargs['env']))
        if '--version' in args:
            return SimpleNamespace(returncode=0, stdout='pocket-tts 3.3.0\n')
        if 'export-voice' in args:
            Path(args[3]).write_bytes(b'synthetic state' * 100)
        if 'generate' in args:
            fake_output_wav(Path(args[args.index('--output-path') + 1]))
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(prep.subprocess, 'run', fake_run)
    prep.prepare(binary, reference, output)
    assert output.read_bytes() == b'synthetic state' * 100
    assert len(commands) == 3
    assert all(env['HF_ENDPOINT'] == 'http://127.0.0.1:9' for args,env in commands)
    with pytest.raises(prep.PreparationError):
        prep.prepare(binary, reference, output)


def test_first_download_is_explicit_and_offline_verification_stays_offline(tmp_path, monkeypatch):
    binary = tmp_path / 'pocket-tts.exe'; binary.write_bytes(b'stub')
    ref = tmp_path / 'synthetic.wav'; synthetic_wav(ref)
    output = tmp_path / 'private' / 'voice.safetensors'
    endpoints = []
    def fake_run(args, **kwargs):
        endpoints.append(kwargs['env']['HF_ENDPOINT'])
        if '--version' in args: return SimpleNamespace(returncode=0, stdout='pocket-tts 3.3.0')
        if 'export-voice' in args: Path(args[3]).write_bytes(b'a'*256)
        if 'generate' in args: fake_output_wav(Path(args[args.index('--output-path') + 1]))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(prep.subprocess, 'run', fake_run)
    prep.prepare(binary, ref, output, allow_download=True)
    assert endpoints == ['http://127.0.0.1:9', 'https://huggingface.co', 'http://127.0.0.1:9']


def test_failed_export_cannot_publish_profile(tmp_path, monkeypatch):
    binary = tmp_path / 'pocket-tts.exe'; binary.write_bytes(b'stub')
    ref = tmp_path / 'synthetic.wav'; synthetic_wav(ref)
    output = tmp_path / 'private' / 'voice.safetensors'
    def fake_run(args, **kwargs):
        return SimpleNamespace(returncode=0 if '--version' in args else 1,
                               stdout='pocket-tts 3.3.0' if '--version' in args else '')
    monkeypatch.setattr(prep.subprocess, 'run', fake_run)
    with pytest.raises(prep.PreparationError): prep.prepare(binary, ref, output)
    assert not output.exists()
    assert list(output.parent.glob('*')) == []


@pytest.mark.parametrize('duration,amplitude', [(1, 1200), (5, 0), (31, 1200)])
def test_reject_invalid_reference(tmp_path, duration, amplitude):
    ref = tmp_path / 'reference.wav'; synthetic_wav(ref, duration=duration, amplitude=amplitude)
    with pytest.raises(prep.PreparationError): prep._validate_wav(ref)


def test_failed_offline_generation_leaves_no_private_profile(tmp_path, monkeypatch):
    binary = tmp_path / 'pocket-tts.exe'; binary.write_bytes(b'stub')
    ref = tmp_path / 'reference.wav'; synthetic_wav(ref)
    output = tmp_path / 'private' / 'voice.safetensors'
    def fake_run(args, **kwargs):
        if '--version' in args:
            return SimpleNamespace(returncode=0, stdout='pocket-tts 3.3.0')
        if 'export-voice' in args:
            Path(args[3]).write_bytes(b'synthetic' * 40)
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(prep.subprocess, 'run', fake_run)
    with pytest.raises(prep.PreparationError, match='hors ligne'):
        prep.prepare(binary, ref, output)
    assert not output.exists()
    assert list(output.parent.iterdir()) == []


def test_reject_output_inside_git_worktree(tmp_path):
    root = tmp_path / 'checkout'
    root.mkdir()
    (root / '.git').mkdir()
    with pytest.raises(prep.PreparationError, match='dépôt Git'):
        prep._check_private_location(root / 'private' / 'voice.safetensors')


def test_mismatched_binary_version_never_attempts_export(tmp_path, monkeypatch):
    binary = tmp_path / 'pocket-tts.exe'; binary.write_bytes(b'stub')
    ref = tmp_path / 'reference.wav'; synthetic_wav(ref)
    output = tmp_path / 'private' / 'voice.safetensors'
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='pocket-tts 0.0.0')
    monkeypatch.setattr(prep.subprocess, 'run', fake_run)
    with pytest.raises(prep.PreparationError, match='version'):
        prep.prepare(binary, ref, output, allow_download=True)
    assert len(calls) == 1
    assert calls[0][-1] == '--version'
    assert not output.exists()
