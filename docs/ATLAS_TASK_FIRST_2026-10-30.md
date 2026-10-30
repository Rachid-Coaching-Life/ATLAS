# ATLAS — Assistant orienté tâches et visage vivant

Date : 30 octobre 2026. Branche autorisée : `develop-atlas`.

## Retour du test utilisateur

L'utilisateur a confirmé une interface holographique affichée avec le
portrait d'origine. En usage réel, il constate une latence trop forte, des
introductions répétées, une demande orale incorrectement transcrite et des
animations faciales insuffisantes. Il précise que l'objectif principal est
**d'exécuter des tâches utiles**, pas d'entretenir une conversation.

La capture de la dernière demande montre une phrase déformée par la
transcription (« longue affrontesse normale ») ; les causes de cette erreur
de reconnaissance et de la latence totale **ne sont pas établies**.
Aucun changement de modèle ni de configuration audio n'est justifié par
la capture seule.

## Audit du code

1. `src/jarvis/system_prompt.py` imposait encore une personnalité de
   majordome britannique bavard, avec humour et commentaire supplémentaire.
2. `src/jarvis/reply/engine.py` sait fournir une présentation courte
   sur demande explicite. Le modèle peut néanmoins générer une amorce
   répétitive non sollicitée ; l'identité du prompt pouvait aussi suivre
   un mot d'activation historique.
3. `src/jarvis/tasks.py` et `src/desktop_app/task_centre.py` possèdent
   **déjà** une file de tâches, des accusés de réception, un suivi et une
   annulation. Il faut les rendre accessibles sans un second moteur.
4. `src/desktop_app/face_widget.py` possède un minuteur de clignement,
   mais ne le dessinait que sur le visage géométrique ancien. Le portrait
   PNG n'animait que la bouche lorsque la synthèse vocale publiait son
   état ou son enveloppe PCM. Il ne dispose pas de visèmes phonétiques,
   de calques de sourire ni de squelette facial.

## Modifications réalisées

| Fichier | Modification | Justification |
|---|---|---|
| `src/jarvis/system_prompt.py` | Instructions françaises orientées exécution, brèves, sans humour ni auto-présentation récurrente | Usage principal = tâches réelles |
| `src/jarvis/reply/engine.py` | Identité de l'assistant fixée à ATLAS ; suppression très ciblée d'une présentation répétée placée devant une autre réponse ; clarification si seule la présentation était produite | Réponses plus directes, sans modification des résultats d'outils |
| `src/jarvis/daemon.py` | Un seul message de présentation en file TTS au **démarrage normal** ; rien durant le smoke test ni par réponse | Séparer la présentation de la réponse opérationnelle |
| `src/desktop_app/hologram_panel.py` | Nouveau bouton **TÂCHES** (abrégé sur les petites tailles) et signal associé | Accès immédiat aux tâches depuis l'hologramme |
| `src/desktop_app/app.py` | Connexion du bouton au **centre des tâches existant** | Aucune duplication de file ni de moteur IA |
| `src/desktop_app/task_centre.py` | Titres et actions visibles francisés et attribués à ATLAS | Interface compréhensible et identité cohérente |
| `src/desktop_app/face_widget.py` | Clignement des paupières projeté uniquement durant la fermeture des yeux sur le portrait original | Donner vie au portrait sans modifier le PNG, sa place ou ses dimensions |

Tests ajoutés ou actualisés :
`tests/test_system_prompt.py`,
`tests/test_atlas_reply_style.py`,
`tests/test_hologram_controls.py`,
`tests/test_atlas_portrait.py`,
`tests/test_task_centre.py`.

## Frontières de validation

- Le portrait image `atlas_portrait.png` n'a pas été modifié.
- Le contrôle de clignement est temporel et réversible, mais **son
  naturel visuel doit être observé dans la vraie fenêtre**.
- La bouche est déjà animée à partir de l'énergie audio TTS ; ce n'est
  **pas** une synchronisation phonème/visème. Un sourire naturel
  demanderait un travail graphique séparé de morphing ou de calques
  approuvés, et n'est **pas encore livré**.
- La latence et l'erreur de reconnaissance vocale restent **non mesurées**.
  Les changements de prompt ne prouvent pas à eux seuls un gain de
  vitesse ni de compréhension.
- Ces changements sont enregistrés sur GitHub mais les nouveaux tests
  Windows ne sont **pas encore exécutés**.

## Validation ciblée Windows

```powershell
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_system_prompt.py tests/test_atlas_reply_style.py tests/test_hologram_controls.py tests/test_atlas_portrait.py tests/test_task_centre.py
```

En fonctionnement réel : vérifier l'accès à **TÂCHES**, lancer une
action non destructive, observer son statut et son résultat, confirmer
que la présentation n'est prononcée qu'une fois au démarrage, et
observer les paupières après plusieurs secondes d'inactivité active.
Ne pas déclarer ces comportements validés avant retour utilisateur.

## Étape suivante

Priorité métier : définir trois à cinq actions locales réellement
utiles puis vérifier leurs permissions, leur exécution, leur retour de
statut et leurs erreurs. Diagnostiquer séparément les phases de latence
(Whisper, routage/planification, modèle, outils, TTS) avant tout
changement de modèle. Pour sourire et phonèmes, prévoir un travail
graphique/visème dédié, préservant la photographie d'origine.


## 30 octobre 2026 — Exécution rapide de tâches depuis l'hologramme

**Validation utilisateur :** après la correction des attentes de test
sur la suppression d'une auto-présentation répétée, les six scénarios
de `tests/test_atlas_reply_style.py` ont réussi sur Windows
(`6 passed in 2.27s`). Cette validation porte sur le filtrage
de la présentation et le message de démarrage, pas sur l'exécution
réelle des tâches.

### Audit préalable

L'hologramme proposait déjà **TÂCHES** mais le bouton ouvrait
uniquement la fenêtre `TaskCentreWindow`. Le centre gère la
soumission corrélée par `request_id`, l'accusé de réception
`__TASK__`, l'état de chaque tâche, les résultats, les annulations
et le brouillon en cours. Le moteur `TaskManager` accepte déjà
les tâches à travers `ATLASSystemTray.submit_task`.
Créer un autre gestionnaire d'actions aurait introduit des
conflits de files, de suivi et de confirmations.

### Modification minimale

- `src/desktop_app/hologram_panel.py` : clic **gauche** sur
  `TÂCHES` = centre existant, clic **droit** =
  `Nouvelle tâche…`; émission de `task_input_requested`.
  Les cartes affichent la dernière instruction et des **états de
  tâche** explicitement nommés, alimentés par les événements du
  centre. `Traitement terminé` ne prétend pas qu'une opération
  sur le système a été vérifiée : le texte du résultat reste
  consultable dans le centre.
- `src/desktop_app/app.py` : saisie temporaire focalisable
  (`QInputDialog`, la projection reste sans focus), appel
  `TaskCentreWindow.submit_hologram_task`. Si ATLAS ne tourne pas,
  si une soumission attend son accusé ou si la saisie est annulée,
  aucune tâche n'est envoyée. Connexion des signaux de tâches
  existantes au panneau, sans ajouter un deuxième backend.
- `src/desktop_app/task_centre.py` : réemploi de la même
  routine `_submit_prompt` depuis la fenêtre et l'hologramme,
  même identifiant et même temporisation d'accusé de réception.
  Le brouillon en cours reste inchangé lorsqu'une tâche est
  soumise depuis l'hologramme. Les erreurs et résultats sont
  redigés avant affichage ; les libellés de statut sont français.
- `tests/test_task_centre.py` et
  `tests/test_hologram_controls.py` : tests d'intégration
  de la voie rapide, du refus, de l'absence de doublon,
  du brouillon préservé, du suivi des transitions de statut,
  du résultat consultable dans le centre et de l'annulation
  de la boîte de saisie.

### Portée et limites

- Une tâche « terminée » signifie que le service de tâches a
  produit un résultat ; ce n'est pas une preuve automatique
  qu'une modification de fichier ou de système a eu lieu.
- La confirmation de tâches potentiellement destructives reste
  régie par les protections et autorisations des outils existants,
  qui doivent être auditées tâche par tâche.
- En cas de nombreuses tâches simultanées, l'hologramme affiche
  la **dernière mise à jour** reçue. Le centre garde la liste et
  les résultats complets.
- Aucune modification du portrait, de sa taille, de sa géométrie,
  de son image, ni de la branche `main`.
- Les nouveaux tests ne sont **pas encore exécutés sur Windows**.

### Validation ciblée

```powershell
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_task_centre.py tests/test_hologram_controls.py
```

Ensuite, sous ATLAS normal : clic droit sur **TÂCHES**,
`Nouvelle tâche…`, une instruction non destructive, vérifier
qu'elle est transmise et que les états de tâche proviennent bien
du service. Clic gauche sur **TÂCHES** pour consulter la réponse
intégrale et son historique.


## 30 octobre 2026 — Première tâche locale déterministe

**Validation utilisateur précédente :** après récupération du commit
`a8e00f0`, les suites `test_task_centre.py` et
`test_hologram_controls.py` ont réussi sous Windows :
`36 passed in 3.10s`.

### Déficit fonctionnel établi

Le gestionnaire de tâches `TaskManager` confiait tous les prompts à
`run_reply_engine`. Or les outils intégrés accessibles par ce moteur
ne comportaient pas de diagnostic de ressources CPU/RAM/disque. Une
demande « Vérifie mon ordinateur » risquait donc de produire une réponse
explicative sans mesure, plutôt qu'une opération démontrée. Les outils
existants de lecture/écriture de fichiers et le moteur de tâches restent
inchangés pour les autres demandes.

### Fonction ajoutée

Commande à saisir dans **TÂCHES** ou **Nouvelle tâche…** :
**`Diagnostic système`** (et quelques variantes strictement définies
telles que `État du système`).

- `src/jarvis/tools/builtin/system_status.py` : nouvel outil intégré
  `systemStatus` de **lecture seule** ; il relève un échantillon
  d'utilisation CPU de 0,1 seconde, la RAM utilisée et totale, et la
  capacité libre du volume du profil utilisateur via `psutil`, déjà
  présent dans `requirements.txt`. Le résultat précise ses limites :
  ni température ni GPU, et aucune conclusion sur la santé matérielle.
- `src/jarvis/tools/registry.py` : publication de l'outil pour le
  routage normal, sans ajouter de dépendance.
- `src/jarvis/tasks.py` : **seulement** pour une commande de statut
  système exacte et non composée, le gestionnaire appelle directement
  le même outil `systemStatus` ; il n'appelle alors ni LLM,
  ni agent de planification. Il conserve les états
  `queued → running → completed` et le texte issu des mesures.
  Un relevé impossible devient `failed` avec l'erreur, jamais
  `completed`. Les commandes composées et actions sur fichiers
  conservent l'ancien trajet moteur/permissions.
- `tests/test_system_status.py` : mesures fictives maîtrisées,
  annonce explicite des limites, absence d'appel LLM, transitions
  du gestionnaire, défaut des compteurs et frontière étroite des
  commandes routées sans modèle.

Le résultat est visible dans le **centre des tâches** et le panneau
holographique par les signaux `task_updated` déjà ajoutés. Le texte
complet reste accessible par le centre.

### État des vérifications

Code et tests enregistrés sur `develop-atlas`, mais les nouveaux
tests Windows ne sont **pas encore exécutés**. Les valeurs réelles du
GTR7, l'exactitude du relevé en situation native et le circuit
complet de lancement ne sont **pas encore confirmés**.
Aucune mesure ni aucun état sain n'est inventé.

Validation recommandée :

```powershell
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_system_status.py tests/test_task_centre.py tests/test_hologram_controls.py
```

Puis, ATLAS démarré : clic droit sur **TÂCHES** →
**Nouvelle tâche…** → `Diagnostic système` ; ouvrir ensuite
**TÂCHES** pour observer la mesure locale, le statut et les
limitations explicitement affichées. Ne pas interpréter ce
relevé comme un test matériel.
