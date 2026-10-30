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
