"""Prepare one private French Pocket TTS voice profile on the user's machine.

Never upload a reference recording or voice state. Require explicit permission
before allowing the official executable to retrieve model weights from HF.
"""
from __future__ import annotations

import argparse
import array
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave


EXPECTED_BINARY_VERSION = 'pocket-tts 3.3.0'  # Rust asset shipped in repo release v4.0.1.
SMOKE_TEXT = 'Bonjour, je suis Atlas et je peux maintenant lire cette phrase en français.'


class PreparationError(Exception):
    """Safe error message: never contains a private file path."""


def _offline_env() -> dict[str, str]:
    env = os.environ.copy()
    env['HF_ENDPOINT'] = 'http://127.0.0.1:9'
    env['HF_HUB_OFFLINE'] = '1'
    env['HF_DATASETS_OFFLINE'] = '1'
    return env


def _download_env() -> dict[str, str]:
    env = os.environ.copy()
    env['HF_ENDPOINT'] = 'https://huggingface.co'
    env.pop('HF_HUB_OFFLINE', None)
    env.pop('HF_DATASETS_OFFLINE', None)
    return env


def _check_private_location(path: Path) -> None:
    """Reject Git worktrees so generated identity data cannot be committed."""
    path = path.resolve(strict=False)
    for ancestor in (path.parent, *path.parent.parents):
        if (ancestor / '.git').exists():
            raise PreparationError('Le profil vocal ne peut pas être créé dans un dépôt Git.')


def _validate_wav(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise PreparationError('Référence WAV privée absente ou invalide.')
    try:
        with wave.open(str(path), 'rb') as reader:
            rate = reader.getframerate()
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            duration = reader.getnframes() / rate if rate else 0
            if channels != 1 or width != 2 or not 8000 <= rate <= 96000 or not 5 <= duration <= 30:
                raise PreparationError('La référence doit être un WAV mono 16 bits de 5 à 30 secondes.')
            pcm = reader.readframes(reader.getnframes())
            if len(pcm) != reader.getnframes() * 2:
                raise PreparationError('La référence WAV est tronquée.')
        samples = array.array('h')
        samples.frombytes(pcm)
        rms = math.sqrt(sum(value * value for value in samples) / len(samples))
        if rms < 50:
            raise PreparationError('La référence WAV contient trop peu de signal vocal.')
    except (wave.Error, EOFError, OSError, ZeroDivisionError, ValueError):
        raise PreparationError('Référence WAV impossible à lire.') from None


def _validate_generated_wav(path: Path) -> None:
    try:
        with wave.open(str(path), 'rb') as reader:
            rate, channels, width = (reader.getframerate(), reader.getnchannels(), reader.getsampwidth())
            frames = reader.getnframes()
            if (channels != 1 or width != 2 or not 8000 <= rate <= 48000
                    or not 0.2 <= frames / rate <= 60):
                raise PreparationError('La génération de contrôle a produit un WAV invalide.')
            pcm = reader.readframes(frames)
            if len(pcm) != frames * 2:
                raise PreparationError('La génération de contrôle a produit un WAV tronqué.')
        audio = array.array('h')
        audio.frombytes(pcm)
        if max(map(abs, audio)) <= 50:
            raise PreparationError('La génération de contrôle a produit du silence.')
    except (wave.Error, EOFError, OSError, ZeroDivisionError, ValueError):
        raise PreparationError('Le WAV de contrôle n’a pas pu être vérifié.') from None


def _call(binary: Path, args: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([str(binary), *args], capture_output=True,
                              text=True, encoding='utf-8', errors='replace',
                              timeout=timeout, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise PreparationError('Pocket TTS ne peut pas exécuter cette étape localement.') from None


def prepare(binary: Path, reference: Path, output: Path, *, allow_download: bool = False) -> None:
    if (not binary.is_absolute() or binary.is_symlink()
            or not binary.is_file() or not reference.is_absolute() or not output.is_absolute()):
        raise PreparationError('Utiliser uniquement des chemins absolus vers des fichiers locaux.')
    _check_private_location(output)
    _validate_wav(reference)
    if output.suffix.lower() != '.safetensors' or output.exists():
        raise PreparationError('Le profil doit être un nouveau fichier .safetensors (aucun écrasement).')
    if output.parent.is_symlink():
        raise PreparationError('Le dossier vocal privé ne doit pas être un lien symbolique.')
    check = _call(binary, ['--version'], _offline_env(), 10)
    if check.returncode or check.stdout.strip() != EXPECTED_BINARY_VERSION:
        raise PreparationError('La version de l’exécutable Pocket TTS ne correspond pas à la version qualifiée.')
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_profile = None
    tmp_wav = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.atlas-pocket-', suffix='.safetensors',
                                         dir=output.parent, delete=False) as f:
            tmp_profile = Path(f.name)
        with tempfile.NamedTemporaryFile(prefix='.atlas-pocket-test-', suffix='.wav',
                                         dir=output.parent, delete=False) as f:
            tmp_wav = Path(f.name)
        env = _download_env() if allow_download else _offline_env()
        export = _call(binary, ['export-voice', str(reference), str(tmp_profile),
                                '--language', 'french', '--quiet'], env, 600)
        if export.returncode or not tmp_profile.is_file() or tmp_profile.stat().st_size < 128:
            raise PreparationError('Export impossible : vérifier l’accès aux poids français avec clonage et leur cache.')
        # This second step MUST remain offline, even when the initial export
        # was explicitly authorised to retrieve weights once.
        speak = _call(binary, ['generate', '--language', 'french',
                               '--voice', str(tmp_profile), '--text', SMOKE_TEXT,
                               '--output-path', str(tmp_wav), '--quiet'], _offline_env(), 180)
        if speak.returncode:
            raise PreparationError('Le profil n’a pas pu générer une phrase hors ligne.')
        _validate_generated_wav(tmp_wav)
        if output.exists():
            raise PreparationError('Profil déjà présent : aucun écrasement autorisé.')
        # Atomic publication that cannot replace an existing private profile,
        # even if another process created it after the existence check.
        try:
            os.link(tmp_profile, output)
        except FileExistsError:
            raise PreparationError('Profil déjà présent : aucun écrasement autorisé.') from None
        except OSError:
            raise PreparationError('Impossible de publier le profil vocal en lieu privé.') from None
    finally:
        for item in (tmp_profile, tmp_wav):
            if item is not None:
                item.unlink(missing_ok=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Préparation locale et privée d’un profil Pocket TTS français')
    p.add_argument('--binary', type=Path, required=True, help='Chemin absolu du binaire officiel vérifié')
    p.add_argument('--reference-wav', type=Path, required=True, help='WAV personnel local de 5 à 30 s')
    p.add_argument('--output', type=Path, required=True, help='Nouveau fichier .safetensors hors Git')
    p.add_argument('--allow-initial-download', action='store_true',
                   help='Autorise explicitement la récupération initiale des poids HF après acceptation des conditions')
    args = p.parse_args(argv)
    try:
        prepare(args.binary, args.reference_wav, args.output,
                allow_download=args.allow_initial_download)
    except PreparationError as exc:
        print(f'Préparation refusée : {exc}', file=sys.stderr)
        return 1
    print('Profil français créé localement. WAV de contrôle vérifié hors ligne.')
    print('Fidélité au timbre et latence sur GTR7 : non vérifiées.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
