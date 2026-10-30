# ATLAS — Audit de migration du nom interne

Date : 30 octobre 2026. Branche : `develop-atlas`. Source : sortie utilisateur de `git grep -in -e jarvis develop-atlas -- ':!*.lock'` au commit `10bf77b`.

## Résultat factuel

- 4 488 lignes contenant le terme, dans 509 fichiers suivis.
- Répartition par racine : `tests/` 2 928 ; `evals/` 581 ; `src/` 529 ; `scripts/` 109 ; `docs/` 89 ; autres 252.
- Mesures non exclusives : 2 764 lignes avec import ou référence de module Python ; 183 lignes avec variable d'environnement historique. Ces nombres **se recoupent** et ne décrivent pas des tâches individuelles.

## Dépendances critiques observées

1. `src/jarvis/` est le paquet Python actuel. `src/desktop_app/app.py` importe notamment sa configuration, son daemon, ses tâches et son état.
2. Les points d'entrée `scripts/run_windows.ps1` et `src/desktop_app/app.py` lancent actuellement `jarvis.daemon` ou `jarvis.main`.
3. `jarvis_desktop.spec` inclut les modules Python en tant qu'importations explicites et nomme le binaire construit.
4. `installer/windows/jarvis_setup.iss` et les workflows GitHub pointent vers les noms actuels des exécutables et des distributions.
5. `src/desktop_app/updater.py` dépend de noms d'archives et d'un dépôt amont historiques. Ne pas modifier ces références avant de définir la stratégie de distribution ATLAS.
6. Les chemins de configuration, base de données, verrous et logs comportent le nom historique. Préserver les données existantes : lecture/migration contrôlées, sauvegarde et tests.
7. `tests/test_voice_listener.py` reste bloqué selon le retour Windows sur le scénario de fréquence native ; la suite complète n'a pas abouti. Cela n'est pas une preuve d'échec des autres tests.

## Ordre obligatoire

1. Établir les points d'entrée et tests de démarrage Windows, en corrigeant ou isolant le test vocal bloquant **sans masquer une régression de capture**.
2. Préparer un changement cohérent de `src/jarvis` vers `src/atlas`, des imports Python dans `src/`, `tests/`, `evals/`, scripts et manifestes. Ne pas appliquer seulement une partie des imports.
3. Migrer les symboles publics et internes (état, thème, gestionnaire, constantes), corriger les patchs de tests et détecter les imports dynamiques.
4. Définir des chemins ATLAS pour configuration et données avec sauvegarde, migration idempotente, priorité claire et test de non-perte.
5. Basculer empaquetage, installateur, mises à jour et workflows exclusivement sur le dépôt autorisé ; **ne pas lancer de publication automatique sur `main`**.
6. Mettre à jour textes visibles, scripts, exemples et documentation active. Préserver séparément les archives de décisions historiques lorsque leur contenu doit rester traçable.
7. Exécuter import checks, tests ciblés, suite unitaire, démarrage réel, écoute, commande vocale de recherche/ouverture de fichier, puis packaging Windows. Aucune réussite non exécutée ne doit être annoncée.

## Statut

**Audit documentaire terminé ; migration structurelle non effectuée.** Une recherche textuelle seule ne prouve ni l'exhaustivité des références dynamiques ni la validité des migrations. Attendre la validation de chaque lot avant de poursuivre.
