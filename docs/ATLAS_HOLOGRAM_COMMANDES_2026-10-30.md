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


## Retour des tests Windows : correction du scénario IPC

Après l'intégration de la commande « ARRÊTER », l'utilisateur a exécuté
`tests/test_hologram_controls.py` et `tests/test_chat_window.py` :
**78 tests réussis, 1 échec (6,28 s)**. L'échec était localisé
dans `test_ipc_created_chat_forwards_reply_to_hologram` avec
`AttributeError: 'types.SimpleNamespace' object has no attribute 'hologram'`.

**Audit :** le vrai constructeur de `FaceWindow` dans
`src/desktop_app/face_widget.py` crée bien
`self.hologram = HologramPanel(self)` lorsque
`_hologram_enabled=True`. Le test avait conservé une simulation
incomplète de ce contrat après l'ajout du signal d'activité du chat.

**Correction minimale, uniquement dans `tests/test_chat_window.py` :**
la simulation comporte désormais `hologram.set_chat_response_pending`.
Le scénario envoie un événement IPC `start` puis `complete` et vérifie
les transitions `[True, False]`, tout en vérifiant le texte de la
réponse et le callback de contrôle existant.

Aucun changement applicatif, aucune modification du moteur de
conversation, du portrait ou des commandes vocales. L'exécution Windows
de ce test après correction reste à confirmer.
