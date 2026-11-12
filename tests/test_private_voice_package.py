"""Qualify the exact final code-only ZIP; never use a personal WAV or token."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/atlas_voice_package_19e0d47'
COMMIT = '19e0d47ddb58c4ffaa0d70dae12518ad2ffe3946'
ZIP_SHA256 = '210c54d8669f73ee415fa4d89c1def2e3fa27e3671ef3a5d5fa3c3ea85edfc76'
ZIP_NAME = 'ATLAS_VOIX_PRIVEE_19e0d47_SANS_WAV.zip'
FILES = (
    'CONTENU.json', 'LIRE_AVANT_UTILISATION.md',
    'PREPARER_MA_VOIX_ATLAS.cmd', 'SHA256SUMS.txt',
    'scripts/atlas_voice_setup.py', 'scripts/prepare_pocket_voice.py',
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def rebuild_exact_zip(destination):
    """Use pinned public Git blobs and code-only metadata, not an uploaded ZIP.

    The fixed final ZIP digest is mandatory: a different compression result or
    metadata byte is a failure, not a substitute qualification of another ZIP.
    """
    payloads = {name: (FIXTURES / name).read_bytes().replace(b'\r\n', b'\n')
                for name in FILES if (FIXTURES / name).is_file()}
    sources = {
        'PREPARER_MA_VOIX_ATLAS.cmd': 'scripts/PREPARER_MA_VOIX_ATLAS.cmd',
        'scripts/atlas_voice_setup.py': 'scripts/atlas_voice_setup.py',
        'scripts/prepare_pocket_voice.py': 'scripts/prepare_pocket_voice.py',
    }
    for target, source in sources.items():
        blob = subprocess.check_output(['git', 'show', COMMIT + ':' + source], cwd=ROOT)
        payloads[target] = blob.replace(b'\n', b'\r\n') if target.endswith('.cmd') else blob
    stamp = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', COMMIT], cwd=ROOT))
    timestamp = datetime.fromtimestamp(stamp, timezone.utc).timetuple()[:6]
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=timestamp)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payloads[name], compresslevel=9)
    actual = sha256(destination.read_bytes())
    if actual != ZIP_SHA256:
        print('::error title=ATLAS ZIP identity::Expected=' + ZIP_SHA256 + '; observed=' + actual)
    assert actual == ZIP_SHA256
    return destination


def verify_zip(archive_path):
    assert sha256(archive_path.read_bytes()) == ZIP_SHA256
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert tuple(sorted(archive.namelist())) == FILES
        manifest = json.loads(archive.read('CONTENU.json'))
        assert manifest['source_commit'] == COMMIT
        assert sorted(manifest['files']) == list(FILES)
        assert manifest['personal_voice_included'] is False
        for line in archive.read('SHA256SUMS.txt').decode('ascii').splitlines():
            expected, name = line.split('  ', 1)
            assert sha256(archive.read(name)) == expected
        for item in manifest['scripts']:
            assert sha256(archive.read(item['package_path'])) == item['package_sha256']
        assert not any(name.lower().endswith(('.wav', '.safetensors', '.exe')) for name in archive.namelist())
        return {name: sha256(archive.read(name)) for name in FILES}


def test_final_zip_rebuild_matches_delivered_archive(tmp_path):
    archive = rebuild_exact_zip(tmp_path / ZIP_NAME)
    assert len(verify_zip(archive)) == 6


# Loaded before the untouched packaged Python scripts in an isolated child.
# File audit covers Python operations, not Windows background services, native
# interpreter startup/prefetch or the entire host filesystem. Controlled ATLAS
# and HF destinations are also independently snapshotted below.
AUDIT_GUARD = r'''
import os
import sys

root = os.path.normcase(os.path.abspath(os.environ['ATLAS_QUALIFICATION_ROOT']))
log = open(os.environ['ATLAS_QUALIFICATION_AUDIT'], 'a', encoding='utf-8', buffering=1)

def emit(message):
    log.write(message + '\n')

def check_path(value, event):
    if isinstance(value, int) or value is None:
        return
    path = os.path.normcase(os.path.abspath(os.fsdecode(value)))
    try:
        inside = os.path.commonpath([root, path]) == root
    except ValueError:
        inside = False
    if not inside:
        emit('OUTSIDE_WRITE ' + event)
        raise PermissionError('Qualification forbids writes outside temporary root')
    emit('INSIDE_WRITE ' + event)

def audit(event, args):
    if event == 'open':
        mode = args[1] or ''
        flags = args[2] or 0
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if any(c in mode for c in 'wax+') or flags & write_flags:
            check_path(args[0], event)
    elif event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.truncate', 'os.utime'):
        check_path(args[0], event)
    elif event in ('os.rename', 'os.link', 'os.symlink'):
        check_path(args[0], event)
        check_path(args[1], event)
    elif event.startswith('socket.') and event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo'):
        emit('NETWORK_ATTEMPT')
        raise RuntimeError('Qualification forbids network access')
    elif event == 'subprocess.Popen':
        emit('ENGINE_PROCESS_ATTEMPT')
        raise RuntimeError('Missing WAV must not start an engine process')

sys.addaudithook(audit)
emit('GUARD_LOADED')
import getpass

def forbidden_prompt(*args, **kwargs):
    emit('TOKEN_PROMPT_ATTEMPT')
    raise RuntimeError('Qualification forbids credential prompts')

getpass.getpass = forbidden_prompt
emit('GUARD_READY')
'''


def snapshot(directory):
    return {str(path.relative_to(directory)): (path.stat().st_size,
            path.stat().st_mtime_ns, sha256(path.read_bytes()))
            for path in directory.rglob('*') if path.is_file()}


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows and real cmd.exe required')
def test_final_zip_native_windows_without_wav(tmp_path, record_property):
    root = tmp_path / 'Qualification finale avec espaces'
    root.mkdir()
    archive = rebuild_exact_zip(root / ZIP_NAME)
    expected_hashes = verify_zip(archive)
    extracted = root / 'Paquet extrait avec espaces'
    extracted.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(extracted)
    assert sorted(str(p.relative_to(extracted)).replace('\\', '/')
                  for p in extracted.rglob('*') if p.is_file()) == list(FILES)
    for name, expected in expected_hashes.items():
        assert sha256((extracted / name).read_bytes()) == expected
    assert (extracted / 'scripts/atlas_voice_setup.py').is_file()
    assert (extracted / 'scripts/prepare_pocket_voice.py').is_file()
    assert not (extracted / 'ATLAS_reference_vocale_C04_15s_candidate.wav').exists()

    controlled = root / 'Emplacements controles'
    appdata = controlled / 'LocalAppData'
    hf_home = controlled / 'HF'
    appdata.mkdir(parents=True)
    hf_home.mkdir()
    (appdata / 'configuration-synthetique.txt').write_bytes(b'unchanged synthetic sentinel')
    (hf_home / 'cache-synthetique.txt').write_bytes(b'no token and no model')
    before = snapshot(controlled)
    guard = root / 'Instrumentation'; guard.mkdir()
    (guard / 'sitecustomize.py').write_text(AUDIT_GUARD, encoding='utf-8')
    audit_log = root / 'audit-applicatif.txt'
    env = os.environ.copy()
    for key in ('HF_TOKEN', 'HUGGINGFACE_HUB_TOKEN', 'HUGGING_FACE_HUB_TOKEN',
                'GH_TOKEN', 'GITHUB_TOKEN', 'PYTHONPYCACHEPREFIX'):
        env.pop(key, None)
    env.update({
        'PYTHONPATH': str(guard), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1',
        'ATLAS_QUALIFICATION_ROOT': str(root), 'ATLAS_QUALIFICATION_AUDIT': str(audit_log),
        'LOCALAPPDATA': str(appdata), 'HF_HOME': str(hf_home),
        'HF_HUB_OFFLINE': '1', 'HF_ENDPOINT': 'http://127.0.0.1:9',
        'TEMP': str(root), 'TMP': str(root),
    })
    # Launch the final CMD and its actual packaged Python, not a stub child.
    completed = subprocess.run(
        ['cmd.exe', '/d', '/c', str(extracted / 'PREPARER_MA_VOIX_ATLAS.cmd')],
        cwd=extracted, env=env, input='\n', capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=30,
    )
    assert completed.returncode == 1, completed.stderr
    assert 'Enregistrement vocal inclus' in completed.stderr
    assert 'introuvable' in completed.stderr
    assert 'Traceback' not in completed.stderr
    assert 'Error in sitecustomize' not in completed.stderr
    assert 'Étape 1' not in completed.stdout
    events = audit_log.read_text(encoding='utf-8').splitlines()
    assert events.count('GUARD_LOADED') == 1, events
    assert events.count('GUARD_READY') == 1, events
    assert not any(e.startswith(('OUTSIDE_WRITE', 'NETWORK_ATTEMPT',
                                'TOKEN_PROMPT_ATTEMPT', 'ENGINE_PROCESS_ATTEMPT')) for e in events), events
    assert not any(e.startswith('INSIDE_WRITE') for e in events), events
    assert snapshot(controlled) == before
    for name, expected in expected_hashes.items():
        assert sha256((extracted / name).read_bytes()) == expected
    assert sha256(archive.read_bytes()) == ZIP_SHA256
    record_property('atlas_final_windows_zip', json.dumps({
        'sha256': sha256(archive.read_bytes()), 'manifest_files': len(expected_hashes),
        'exit_code': completed.returncode, 'windows_native': os.name == 'nt',
        'audit_guard_ready': events.count('GUARD_READY'),
        'network_attempts': events.count('NETWORK_ATTEMPT'),
        'token_prompts': events.count('TOKEN_PROMPT_ATTEMPT'),
        'engine_processes': events.count('ENGINE_PROCESS_ATTEMPT'),
        'outside_python_write_attempts': sum(e.startswith('OUTSIDE_WRITE') for e in events),
        'protected_ATLAS_HF_unchanged': snapshot(controlled) == before,
        'packaged_files_unchanged': all(sha256((extracted / n).read_bytes()) == h
                                      for n, h in expected_hashes.items()),
    }, sort_keys=True))
    print('\n::notice title=ATLAS final Windows ZIP::SHA256=' + ZIP_SHA256
          + '; manifest=6/6; real_CMD_exit=1; missing_WAV_refused=yes; '
          'network_attempts=0; token_prompts=0; engine_processes=0; '
          'audited_outside_Python_writes=0; protected_ATLAS_HF_changes=0; '
          'packaged_files_unchanged=yes; native_Windows=yes')
