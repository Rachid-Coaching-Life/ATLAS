"""Synthetic only: no voice recording, Hugging Face credentials or real model."""
from __future__ import annotations

import importlib.util
import hashlib
import os
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


def trust_synthetic_binary(monkeypatch, binary):
    monkeypatch.setattr(prep, 'EXPECTED_BINARY_SHA256',
                        hashlib.sha256(binary.read_bytes()).hexdigest())


def test_prepare_offline_exports_private_state_without_overwriting(tmp_path, monkeypatch):
    binary = tmp_path / 'pocket-tts.exe'
    binary.write_bytes(b'test')
    trust_synthetic_binary(monkeypatch, binary)
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
    trust_synthetic_binary(monkeypatch, binary)
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
    trust_synthetic_binary(monkeypatch, binary)
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
    trust_synthetic_binary(monkeypatch, binary)
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
    trust_synthetic_binary(monkeypatch, binary)
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


def test_private_destination_rejects_redirected_ancestor(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    if os.name == 'nt':
        import subprocess
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(alias), str(real)],
                       check=True, capture_output=True)
    else:
        alias.symlink_to(real, target_is_directory=True)
    try:
        with pytest.raises(prep.PreparationError):
            prep._check_private_location(alias / 'nested' / 'voice.safetensors')
        assert not list(real.iterdir())
    finally:
        if os.name == 'nt':
            alias.rmdir()
        else:
            alias.unlink()


def test_cleanup_preserves_export_error_and_attempts_wav_removal(tmp_path, monkeypatch, capsys):
    binary = tmp_path / 'engine.exe'; binary.write_bytes(b'stub')
    monkeypatch.setattr(prep, 'EXPECTED_BINARY_SHA256',
                        hashlib.sha256(b'stub').hexdigest(), raising=False)
    reference = tmp_path / 'synthetic.wav'; synthetic_wav(reference)
    output = tmp_path / 'private' / 'voice.safetensors'
    def call(binary, args, env, timeout):
        return SimpleNamespace(returncode=0 if '--version' in args else 1,
                               stdout=prep.EXPECTED_BINARY_VERSION)
    monkeypatch.setattr(prep, '_call', call)
    unlink = Path.unlink
    def locked(path, *args, **kwargs):
        if path.suffix == '.safetensors':
            raise PermissionError('synthetic secret path must not be printed')
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', locked)
    with pytest.raises(prep.PreparationError, match='Export impossible'):
        prep.prepare(binary, reference, output)
    assert not output.exists()
    assert not list(output.parent.glob('.atlas-pocket-test-*.wav'))
    message = capsys.readouterr().err
    assert 'temporaires conservés' in message
    assert str(tmp_path) not in message
    assert 'synthetic secret' not in message


def test_direct_cli_unknown_binary_never_reaches_version(tmp_path, monkeypatch):
    binary = tmp_path / 'engine.exe'; binary.write_bytes(b'unknown')
    reference = tmp_path / 'synthetic.wav'; synthetic_wav(reference)
    monkeypatch.setattr(prep, '_call', lambda *a: pytest.fail('untrusted binary executed'))
    with pytest.raises(prep.PreparationError, match='SHA-256'):
        prep.prepare(binary, reference, tmp_path / 'voice.safetensors')


def test_temporary_creation_does_not_retry_acl_refusal(tmp_path, monkeypatch):
    attempts = []
    def denied(*args, **kwargs):
        attempts.append(True)
        raise PermissionError('synthetic ACL refusal')
    monkeypatch.setattr(prep.os, 'open', denied)
    with pytest.raises(prep.PreparationError, match='accès refusé'):
        prep.new_private_temp(tmp_path, '.synthetic-', '.wav')
    assert len(attempts) == 1


def test_temporary_creation_retries_collision_without_overwriting(tmp_path, monkeypatch):
    existing = tmp_path / '.synthetic-collision.wav'; existing.write_bytes(b'original')
    names = iter(['collision', 'unique'])
    monkeypatch.setattr(prep.secrets, 'token_hex', lambda size: next(names))
    created = prep.new_private_temp(tmp_path, '.synthetic-', '.wav')
    assert created.name == '.synthetic-unique.wav'
    assert existing.read_bytes() == b'original'


def test_cleanup_diagnostic_failure_cannot_replace_primary_error(tmp_path, monkeypatch):
    target = tmp_path / 'synthetic.wav'; target.write_bytes(b'fake')
    def denied(*args, **kwargs):
        raise PermissionError('synthetic lock or unavailable stderr')
    monkeypatch.setattr(Path, 'unlink', denied)
    monkeypatch.setattr(prep, 'print', denied, raising=False)
    with pytest.raises(prep.PreparationError, match='primary error'):
        try:
            raise prep.PreparationError('primary error')
        finally:
            prep.cleanup_temporary_files([('WAV de contrôle', target)], primary_error=True)


def test_reparse_attribute_is_refused_even_without_symlink_mode(tmp_path, monkeypatch):
    ancestor = tmp_path / 'reparse'; ancestor.mkdir()
    lstat = Path.lstat
    def redirected(path):
        info = lstat(path)
        if path == ancestor:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info
    monkeypatch.setattr(Path, 'lstat', redirected)
    with pytest.raises(prep.PreparationError, match='réanalyse'):
        prep._check_private_location(ancestor / 'missing' / 'voice.safetensors')


def test_publication_race_preserves_existing_profile(tmp_path, monkeypatch):
    binary = tmp_path / 'engine.exe'; binary.write_bytes(b'stub')
    trust_synthetic_binary(monkeypatch, binary)
    reference = tmp_path / 'synthetic.wav'; synthetic_wav(reference)
    output = tmp_path / 'private' / 'voice.safetensors'
    def call(binary, args, env, timeout):
        if args[0] == 'export-voice':
            Path(args[2]).write_bytes(b'synthetic' * 50)
        if args[0] == 'generate':
            fake_output_wav(Path(args[args.index('--output-path') + 1]))
        return SimpleNamespace(returncode=0, stdout=prep.EXPECTED_BINARY_VERSION)
    monkeypatch.setattr(prep, '_call', call)
    publish = prep.publish_new_file
    def race(source, target):
        target.write_bytes(b'preexisting-racer')
        return publish(source, target)
    monkeypatch.setattr(prep, 'publish_new_file', race)
    with pytest.raises(prep.PreparationError, match='aucun écrasement'):
        prep.prepare(binary, reference, output)
    assert output.read_bytes() == b'preexisting-racer'
    assert list(output.parent.iterdir()) == [output]


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows file sharing required')
def test_windows_locked_file_cleanup_continues(tmp_path):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    locked = tmp_path / 'synthetic.safetensors'; locked.write_bytes(b'fake state')
    other = tmp_path / 'synthetic.wav'; other.write_bytes(b'fake wav')
    # Share read/write, but not deletion: a real Windows sharing violation.
    handle = kernel.CreateFileW(str(locked), 0x80000000, 3, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        with pytest.raises(prep.PreparationError, match='profil temporaire') as error:
            prep.cleanup_temporary_files(
                [('profil temporaire', locked), ('WAV de contrôle', other)], primary_error=False,
            )
        assert str(tmp_path) not in str(error.value)
        assert locked.exists()
        assert not other.exists()
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows permission failure required')
def test_windows_readonly_file_cleanup_is_reported(tmp_path):
    import stat
    locked = tmp_path / 'synthetic.wav'; locked.write_bytes(b'fake wav')
    other = tmp_path / 'synthetic.safetensors'; other.write_bytes(b'fake state')
    locked.chmod(stat.S_IREAD)
    try:
        with pytest.raises(prep.PreparationError, match='WAV de contrôle'):
            prep.cleanup_temporary_files(
                [('WAV de contrôle', locked), ('profil temporaire', other)], primary_error=False,
            )
        assert locked.exists()
        assert not other.exists()
    finally:
        locked.chmod(stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows ACL enforcement required')
def test_windows_denied_directory_permission_is_sanitised(tmp_path, monkeypatch, capsys):
    import re
    import subprocess
    identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                              capture_output=True, text=True, check=True)
    sid = re.search(r'S-\d+(?:-\d+)+', identity.stdout).group()
    directory = tmp_path / 'private'; directory.mkdir()
    binary = tmp_path / 'engine.exe'; binary.write_bytes(b'stub')
    trust_synthetic_binary(monkeypatch, binary)
    reference = tmp_path / 'synthetic.wav'; synthetic_wav(reference)
    monkeypatch.setattr(prep, '_call', lambda *a: SimpleNamespace(
        returncode=0, stdout=prep.EXPECTED_BINARY_VERSION,
    ))
    denied = subprocess.run(['icacls', str(directory), '/deny', f'*{sid}:(WD)'],
                            capture_output=True, check=True)
    try:
        with pytest.raises(PermissionError):
            (directory / 'write-probe').write_bytes(b'probe')
        result = prep.main(['--binary', str(binary), '--reference-wav', str(reference),
                            '--output', str(directory / 'voice.safetensors')])
        message = capsys.readouterr()
        assert result == 1
        assert 'refusée' in message.err
        assert str(tmp_path) not in message.err
        assert 'Traceback' not in message.err
        assert not (directory / 'voice.safetensors').exists()
    finally:
        subprocess.run(['icacls', str(directory), '/remove:d', f'*{sid}'],
                       capture_output=True, check=True)
