# ATLAS — Contrôle de réponse depuis l'hologramme

Date : 30 octobre 2026. Branche : `develop-atlas`.

## Objectif

Le panneau holographique est une interface de dialogue, pas seulement une
projection d'activité. La fenêtre de chat peut être masquée pendant que le
moteur IA répond ; le panneau doit permettre d'interrompre **cette réponse
écrite** sans ouvrir la fenêtre de conversation.

## Audit des mécanismes existants

- `ChatWindow._stop()` annule déjà la requête par son callback
  `cancel_fn` (processus séparé) ou le moteur local (mode intégré).
- `ChatWindow._set_thinking()` sait quand une requête écrite est en cours.
- `ATLASSystemTray._connect_chat_to_hologram()` relie déjà les réponses
  du chat aux cartes de la projection.
- `FaceWindow` utilise `WindowDoesNotAcceptFocus` : une saisie texte
  directement dans la projection exige un chantier séparé de gestion
  du focus clavier. Aucun champ de saisie non fonctionnel n'est ajouté.

## Fonction livrée

1. `src/desktop_app/hologram_panel.py`
   - Signal `stop_response_requested` ;
   - bouton « ARRÊTER » caché à l'état de repos ;
   - API `set_chat_response_pending(bool)` contrôlant son apparition
     et son activation ; le bouton réutilise le style déjà appliqué
     aux autres commandes de la projection.
2. `src/desktop_app/chat_window.py`
   - signal `query_activity_changed(bool)` à chaque transition
     du suivi de réponse ;
   - émission `False` si le démon devient indisponible pendant
     une réponse.
3. `src/desktop_app/app.py`
   - le signal d'activité du chat commande la visibilité du bouton ;
   - un clic appelle `_handle_hologram_stop_request()`, qui vérifie
     qu'une requête écrite est effectivement en cours puis réutilise
     `ChatWindow._stop()`.
   - aucune commande de suspension/arrêt du démon vocal dans ce chemin.
4. `tests/test_hologram_controls.py`
   - vérification d'une annulation depuis la projection pendant que
     la fenêtre de chat reste masquée ;
   - vérification du retour à l'état repos après la réponse et lors
     de l'indisponibilité du démon ;
   - vérification de l'ignorance d'une réponse tardive après annulation.

## Limites et validation

- Le bouton concerne les **réponses écrites** suivies par ChatWindow,
  et non une réponse vocale issue d'un autre flux.
- Aucune modification du portrait, du modèle IA, des fichiers d'images,
  de la géométrie de FaceWindow ou de la branche `main`.
- Pas de nouvelle dépendance, fenêtre, boucle ou minuterie.
- Une suite de tests Qt a déjà réussi avant l'ajout de cette fonction :
  124 tests passés sur 126, puis les deux tests d'identité corrigés
  et réussis. **Les nouveaux tests d'arrêt doivent encore être exécutés
  sur Windows** ; le fonctionnement natif n'est pas encore confirmé.

### Validation locale

Depuis le dépôt ATLAS :

```powershell
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_hologram_controls.py tests/test_chat_window.py
```

### Validation fonctionnelle attendue

Après démarrage ordinaire d'ATLAS (hors mode diagnostic sans moteur),
ouvrir « ÉCHANGES », envoyer une question écrite, puis masquer la
conversation. Le bouton « ARRÊTER » doit apparaître sur l'hologramme.
Son activation doit interrompre la réponse écrite en cours, afficher
« Réponse interrompue. » et faire disparaître le bouton ; la voix
reste dans son état antérieur.

Ne pas considérer ce comportement comme démontré sans observation
en situation réelle.
