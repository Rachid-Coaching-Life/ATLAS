"""ATLAS — fenêtre Qt native minimale, sans Ollama ni service vocal.

Ce test reste potentiellement risqué sur un GTR7 ayant déjà subi des
coupures d'alimentation brutales : ne pas le répéter en cas d'échec.

Exécution depuis le dépôt :
    .\\.venv\\Scripts\\python.exe scripts\\probe_atlas_native_window.py --seconds 8

Le processus ne lance pas desktop_app.app.main(), le démon vocal, le
setup wizard, Ollama, de test de charge ou de rendu synthétique continu.
L'option --metrics lit seulement les compteurs CPU et mémoire (psutil,
dépendance déjà utilisée par ATLAS). Elle ne mesure pas la consommation
électrique, le GPU ni la température et ne sollicite pas de sous-processus.
Un arrêt sans écran bleu peut empêcher l'écriture de la dernière ligne.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import time

# Variables locales à CE processus uniquement. Pas de modification durable
# des variables PowerShell, de la configuration ou des fichiers graphiques.
os.environ["ATLAS_HOLOGRAM_LOW_EFFECTS"] = "1"
os.environ["ATLAS_HOLOGRAM_CACHED_EFFECTS"] = "1"
os.environ["ATLAS_HOLOGRAM_SCULPTED"] = "1"
os.environ["ATLAS_HOLOGRAM_OPTICAL"] = "1"

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from desktop_app.face_widget import FaceWindow


def journaliser(message: str, destination: Path) -> None:
    """Écrire un repère durable ; ne jamais attendre une file en mémoire."""
    horodatage = datetime.now().astimezone().isoformat(timespec="seconds")
    ligne = f"{horodatage} {message}"
    with destination.open("a", encoding="utf-8") as fichier:
        fichier.write(ligne + "\n")
        fichier.flush()
        os.fsync(fichier.fileno())
    print(ligne, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Essai bref de la fenêtre ATLAS, sans moteur IA")
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument(
        "--metrics", action="store_true",
        help="Journaliser les moyennes CPU de l'intervalle et la mémoire finale (pas le GPU)",
    )
    args = parser.parse_args()
    if not 1 <= args.seconds <= 15:
        parser.error("La durée doit être comprise entre 1 et 15 secondes.")

    log_path = Path(tempfile.gettempdir()) / "ATLAS_native_window_diagnostic.log"
    journaliser(
        "DEBUT essai fenêtre native uniquement ; optique allégé ; aucun moteur vocal/IA lancé",
        log_path,
    )
    application = QApplication.instance() or QApplication([sys.argv[0]])
    application.setQuitOnLastWindowClosed(True)
    fenetre = None
    try:
        fenetre = FaceWindow(hologram=True, portrait=True)
        if fenetre.face._portrait.isNull():
            raise RuntimeError("Portrait ATLAS introuvable — arrêt du test")
        if not fenetre.hologram._optical:
            raise RuntimeError("Mode optique de diagnostic non activé")
        if fenetre.hologram._timer.interval() != 500:
            raise RuntimeError("Cadence de l'hologramme inattendue")

        fenetre.show()
        application.processEvents()
        journaliser(f"FENETRE_AFFICHEE duree_max={args.seconds}s", log_path)
        mesures = None
        if args.metrics:
            # Two snapshots only: no sampling timer, no child process.
            # psutil is already an ATLAS dependency. CPU percent is an
            # interval mean; memory is a final snapshot, never a peak.
            import psutil
            processus = psutil.Process()
            processus.cpu_percent(interval=None)  # prime its clock
            psutil.cpu_percent(interval=None)       # prime system clock
            mesures = (psutil, processus, time.monotonic())

        QTimer.singleShot(args.seconds * 1000, application.quit)
        application.exec()
        journaliser("FIN_RETOUR_BOUCLE_QT", log_path)
        if mesures is not None:
            psutil, processus, debut = mesures
            temps = time.monotonic() - debut
            charge_processus = processus.cpu_percent(interval=None)
            charge_systeme = psutil.cpu_percent(interval=None)
            memoire_processus = processus.memory_info().rss / (1024 * 1024)
            memoire_systeme = psutil.virtual_memory().percent
            journaliser(
                "MESURES_MOYENNES "
                f"duree_s={temps:.2f} "
                f"cpu_processus_pct_un_coeur={charge_processus:.1f} "
                f"cpu_systeme_pct={charge_systeme:.1f} "
                f"ram_processus_fin_mib={memoire_processus:.1f} "
                f"ram_systeme_fin_pct={memoire_systeme:.1f} "
                "gpu_et_temperatures_non_mesures=1",
                log_path,
            )
        return 0
    except Exception as erreur:
        journaliser(f"ERREUR {type(erreur).__name__}: {erreur}", log_path)
        return 1
    finally:
        if fenetre is not None:
            fenetre.close()
        print(f"Journal : {log_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
