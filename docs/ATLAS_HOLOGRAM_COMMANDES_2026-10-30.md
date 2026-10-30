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


## 30 octobre 2026 — Copier une conversation depuis le panneau

**Validation précédente :** le scénario IPC corrigé
`test_ipc_created_chat_forwards_reply_to_hologram` a été exécuté
sur Windows par l'utilisateur : `1 passed in 2.44s`.
Cela confirme le raccordement du test ciblé, sans constituer une
validation manuelle de tous les contrôles de la projection.

**Fonction livrée :** clic droit sur les cartes
`DERNIÈRE DEMANDE` et `RÉPONSE`, puis
`Copier le texte affiché`. Le texte en cours est envoyé dans
le presse-papiers local de Windows exclusivement après cette action.

Audit : le panneau possédait déjà des étiquettes Qt
`QLabel.PlainText` et tronque l'aperçu à 230/250 caractères.
Ajouter un troisième bouton permanent de copie aurait réduit
la place disponible, notamment en vue compacte. Une action contextuelle
sur les étiquettes existantes est moins intrusive.

Fichiers :
- `src/desktop_app/hologram_panel.py` : deux
  `QAction` contextuelles, reliées au presse-papiers Qt par une
  action utilisateur explicite. La copie concerne exactement le
  **texte affiché**, pas forcément une longue réponse intégrale.
- `tests/test_hologram_controls.py` : contrôle que le texte
  reste littéral, que le presse-papiers ne change pas avant action,
  que les mises à jour du contenu sont reprises et que les réponses
  tronquées copient seulement la partie visible.

Invariants : aucune nouvelle fenêtre, service, minuterie ou
dépendance ; aucune modification d'ATLAS portrait, de son image,
de sa taille, de sa position ou de la branche `main`.

**Reste non vérifié :** les nouveaux tests de copie n'ont pas encore
été exécutés dans l'environnement Qt Windows et le menu contextuel
n'a pas encore été observé dans la fenêtre native.

Pour récupérer et vérifier cette petite fonction :

```powershell
git pull --ff-only origin develop-atlas
.\.venv\Scripts\python.exe -m pytest -q tests/test_hologram_controls.py::test_hologram_copy_action_uses_current_visible_plain_text
```


## Développement fonctionnel — saisie rapide depuis l'hologramme

À la suite de la mise à jour locale au commit `5dd300b` confirmée
par l'utilisateur, l'audit a identifié un vrai obstacle : la fenêtre
`FaceWindow` est dotée de `WindowDoesNotAcceptFocus`. Un champ
clavier inséré naïvement dans la projection ne serait donc pas
utilisable de manière fiable sous Windows. Le moteur de chat existant
et la gestion des échanges n'ont pas besoin d'être dupliqués.

**Ajout sur `develop-atlas` :**

- `src/desktop_app/hologram_panel.py` : bouton **ÉCRIRE**
  transmettant `text_input_requested`. En vue compacte (moins
  de 295 px de largeur ou 265 px de hauteur), il affiche `✎` avec
  un nom accessible complet. Pendant une réponse écrite, le bouton
  **ÉCRIRE** s'efface au profit de **ARRÊTER**, afin de ne pas
  surcharger la ligne de commandes.
- `src/desktop_app/app.py` : action temporaire
  `_request_hologram_text()` ouvrant une saisie Qt focalisable,
  uniquement à l'initiative de l'utilisateur. Après validation,
  le texte est transmis au même `ChatWindow` (et donc au même
  moteur conversationnel) sans afficher la fenêtre complète du
  chat. Refus si le service n'est pas lancé ou si un message
  est déjà en traitement ; annuler la boîte de dialogue n'envoie
  aucune requête. La création de `ChatWindow` est centralisée
  dans `_create_chat_window()` pour les trois voies
  (chat ouvert, IPC, saisie holographique).
- `src/desktop_app/chat_window.py` : `submit_prompt(text)`
  revalorise l'envoi existant (`_send()`) sans deuxième
  conversation ; l'amorçage de l'historique vocal a été extrait
  vers `_seed_hot_window_if_needed()` et s'effectue avant
  le premier envoi masqué afin d'éviter sa duplication à
  l'ouverture ultérieure de la fenêtre.
- `tests/test_hologram_controls.py` : saisie validée, annulation,
  réaction de la carte de réponse, disposition compacte,
  et basculement entre **ÉCRIRE** et **ARRÊTER**.
- `tests/test_chat_window.py` : maintien de l'historique vocal
  unique et impossibilité d'envoyer deux requêtes simultanément
  avec `submit_prompt`.

**Limites :** la boîte de saisie est un dialogue Qt temporaire
qui prend le focus, pas un remplacement permanent de l'hologramme.
Elle ne lance ni nouvelle instance du moteur, ni processus externe.
La disposition du portrait et son fichier image ne changent pas.

**Validation :** code et tests enregistrés sur GitHub, mais aucun
essai Qt sur Windows ni test de la fonctionnalité avec le moteur
de dialogue réel n'a encore été effectué après ces changements.

Après `git pull --ff-only origin develop-atlas`, tests ciblés :

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_hologram_controls.py tests/test_chat_window.py
```

Puis, en fonctionnement normal d'ATLAS : cliquer sur **ÉCRIRE**,
taper une demande, valider ; vérifier qu'elle figure dans la carte
`DERNIÈRE DEMANDE`, que `ARRÊTER` apparaît pendant le traitement
et que la réponse arrive dans `RÉPONSE`. Le bouton `ÉCHANGES`
doit ouvrir la même conversation contenant cet échange.
