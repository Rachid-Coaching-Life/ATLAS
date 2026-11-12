"""One-run Windows launcher: pinned Pocket TTS and private local voice state.

No WAV or voice state is uploaded to GitHub. No external Python package is needed.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import zipfile

from prepare_pocket_voice import PreparationError, prepare, EXPECTED_BINARY_VERSION

RELEASE = "https://github.com/kyutai-labs/pocket-tts/releases/download/v4.0.1/pocket-tts-3.3.0-x86_64-pc-windows-msvc.zip"
SHA256 = "98753041f2e65744b989776f87bccb93f1f574a08afe1890c5427ec94cd6309c"
REFERENCE_NAME = "ATLAS_reference_vocale_C04_15s_candidate.wav"


class SetupError(Exception):
    """Safe, path-free and credential-free user facing error."""


def private_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise SetupError("LOCALAPPDATA est indisponible. Lancer ce programme sous Windows.")
    return Path(base) / "ATLAS" / "private" / "pocket"


def _binary_version(binary: Path) -> str:
    try:
        proc = subprocess.run(
            [str(binary), "--version"], capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SetupError("Impossible de vérifier le moteur Pocket TTS.") from None
    if proc.returncode:
        raise SetupError("L’exécutable Pocket TTS ne démarre pas correctement.")
    return proc.stdout.strip()


def install_official_binary(directory: Path) -> Path:
    binary = directory / "engine" / "pocket-tts.exe"
    if binary.is_file():
        if binary.is_symlink() or _binary_version(binary) != EXPECTED_BINARY_VERSION:
            raise SetupError("Exécutable local non conforme. Aucun fichier existant n’a été remplacé.")
        return binary
    binary.parent.mkdir(parents=True, exist_ok=True)
    downloaded = None
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".atlas-pocket-official-", suffix=".zip",
            dir=directory, delete=False,
        ) as temp:
            downloaded = Path(temp.name)
            digest = hashlib.sha256()
            try:
                with urlopen(RELEASE, timeout=50) as response:
                    total = 0
                    while True:
                        block = response.read(1024 * 256)
                        if not block:
                            break
                        total += len(block)
                        if total > 100_000_000:
                            raise SetupError("Archive officielle beaucoup trop grande.")
                        temp.write(block)
                        digest.update(block)
            except (HTTPError, URLError, TimeoutError, OSError):
                raise SetupError("Téléchargement HTTPS du binaire officiel impossible.") from None
        if digest.hexdigest() != SHA256:
            raise SetupError("Empreinte SHA-256 officielle différente : installation refusée.")
        with zipfile.ZipFile(downloaded) as archive:
            candidates = [
                item for item in archive.infolist()
                if item.filename.replace("\\", "/").split("/")[-1] == "pocket-tts.exe"
                and not item.is_dir()
            ]
            if len(candidates) != 1 or not 1_000_000 <= candidates[0].file_size <= 70_000_000:
                raise SetupError("Exécutable attendu absent de l’archive vérifiée.")
            with tempfile.NamedTemporaryFile(
                prefix=".atlas-pocket-exe-", suffix=".tmp",
                dir=binary.parent, delete=False,
            ) as temp:
                staged = Path(temp.name)
                with archive.open(candidates[0]) as source:
                    while True:
                        block = source.read(1024 * 256)
                        if not block:
                            break
                        temp.write(block)
        if binary.exists():
            raise SetupError("Un exécutable existe déjà. Aucun écrasement autorisé.")
        try:
            os.link(staged, binary)
        except OSError:
            raise SetupError("Impossible de publier l’exécutable local vérifié.") from None
        if _binary_version(binary) != EXPECTED_BINARY_VERSION:
            binary.unlink(missing_ok=True)
            raise SetupError("Version effective du moteur non conforme.")
        return binary
    except zipfile.BadZipFile:
        raise SetupError("L’archive officielle téléchargée est invalide.") from None
    finally:
        for path in (downloaded, staged):
            if path is not None:
                path.unlink(missing_ok=True)


def _has_local_hf_auth() -> bool:
    if os.environ.get("HF_TOKEN"):
        return True
    hf_home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    return (hf_home / "token").is_file()


def _prompt_token() -> str:
    print("\nLe navigateur connecté à Hugging Face ne connecte pas automatiquement le moteur local.")
    print("Créer un jeton personnel en LECTURE : https://huggingface.co/settings/tokens")
    print("Ne colle jamais ce jeton dans un chat ou sur GitHub.")
    token = getpass.getpass("Coller ici le jeton (saisie masquée) : ").strip()
    if not token or len(token) < 8:
        raise SetupError("Jeton Hugging Face absent. Aucune voix créée.")
    return token


def provision(bundle_root: Path) -> Path:
    reference = bundle_root / REFERENCE_NAME
    if not reference.is_file() or reference.is_symlink():
        raise SetupError("Enregistrement vocal inclus dans l’archive introuvable.")
    target_dir = private_dir()
    output = target_dir / "voice_french.safetensors"
    if output.exists():
        raise SetupError("Le profil vocal existe déjà. Aucun écrasement autorisé.")
    print("Étape 1 : vérification du moteur officiel Windows et de son empreinte SHA-256.")
    binary = install_official_binary(target_dir)
    existing_token = os.environ.get("HF_TOKEN")
    temporary_token = None
    try:
        if not _has_local_hf_auth():
            temporary_token = _prompt_token()
            os.environ["HF_TOKEN"] = temporary_token
        print("Étape 2 : création du profil depuis ton enregistrement sur ce PC.")
        print("Étape 3 : génération de contrôle hors ligne et nettoyage des fichiers temporaires.")
        try:
            prepare(binary, reference, output, allow_download=True)
        except PreparationError as exc:
            raise SetupError(str(exc)) from None
        print("Profil créé et contrôlé localement. Aucun fichier vocal transmis à GitHub.")
        print("ATLAS n’est pas encore basculé automatiquement vers Pocket TTS.")
        return output
    finally:
        if temporary_token is not None:
            if existing_token is None:
                os.environ.pop("HF_TOKEN", None)
            else:
                os.environ["HF_TOKEN"] = existing_token


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Préparer une fois la voix personnelle d’ATLAS")
    parser.add_argument(
        "--bundle-root", type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    args = parser.parse_args(argv)
    try:
        provision(args.bundle_root.resolve())
        return 0
    except SetupError as exc:
        print(f"\nPréparation interrompue : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
