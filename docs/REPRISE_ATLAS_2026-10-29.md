# ATLAS — Fiche de reprise du 29 octobre 2026

**Projet :** ATLAS, assistant personnel local, francophone et adapté au mini-PC GTR7 sous Windows.  
**Dépôt autorisé :** `Rachid-Coaching-Life/ATLAS`  
**Branche de travail unique :** `develop-atlas`  
**Branche à préserver :** `main`  
**Date de reprise prévue :** vendredi 30 octobre 2026, matin.  
**Nature de cette fiche :** état de travail et plan de validation, pas attestation de fonctionnement.

## 1. Décisions de l'utilisateur à respecter

1. **Construire ATLAS, et non maintenir le produit d'origine.** L'objectif est la nouvelle application ATLAS. Ne pas proposer des évolutions pour l'ancien produit à la place des travaux demandés.
2. **Aucune identité Jarvis dans le code ATLAS final.** Éliminer méthodiquement l'ancien nom des modules, classes, scripts, variables d'environnement, messages, menus, documentation et métadonnées quand ces éléments appartiennent effectivement à ATLAS. Cette consigne constitue un travail **encore à faire**, et non une correction déjà réalisée. Les noms `jarvis`, `JarvisState`, `JarvisSystemTray` et `JARVIS_VOICE_DEBUG` sont encore observables dans l'architecture existante. Ne pas les supprimer par recherche/remplacement aveugle : inventorier les importations, points d'entrée, contrats persistés et tests, puis migrer le nommage sans rompre l'exécution.
3. **Portrait du robot intouchable.** Conserver strictement l'apparence du robot ATLAS, son visage, sa palette, ses dimensions, sa position relative, ses détails mécaniques et son animation labiale. Ne refondre que la fenêtre projetée à gauche et sa connexion visuelle. Les adaptations de disposition exigées sur les petits écrans ne doivent pas déformer le portrait.
4. **Une véritable interface applicative**, pas une image générée, pas une maquette ni une fenêtre rectangulaire à coins arrondis. Les commandes doivent agir sur les services existants.
5. **Arrêt du travail le 29 au soir.** Ne pas lancer les tests sur le PC de l'utilisateur ou de nouveaux travaux de refonte ce soir. Reprendre avec une vérification de l'état de la branche puis une exécution contrôlée le lendemain.

## 2. Direction visuelle demandée

- Silhouette holographique sculpturale, asymétrique, ouverte par des découpes, avec formes fluides et géométriques irrégulières.
- Plexiglas numérique réellement translucide, légèrement teinté, avec reflets, facettes et simulation crédible de profondeur/réfraction. Conserver un contraste suffisant pour les textes.
- Plaques d'information flottantes, superposées, visuellement distinctes, sans reproduire un tableau de bord traditionnel.
- Couleurs coordonnées à ATLAS : bleu électrique et orange ambré, traits lumineux fins, microcircuits et particules discrètes.
- Liaison lumineuse entre les circuits du robot et la fenêtre, impression que les informations émanent du robot. Déploiement animé depuis ATLAS puis stabilisation, avec réactions légères à l'écoute, à la réflexion et à la réponse.
- Adaptation aux tailles d'écran, animation fluide et consommation de ressources raisonnable pour le GTR7.
- Zones nécessaires : **ATLAS / Interface neurale**, état de l'assistant, dernière demande, réponse, activation/contrôle vocal et accès aux échanges.

## 3. Architecture réellement constatée dans `develop-atlas`

**Constaté par lecture du dépôt GitHub, pas par exécution Windows :**

- `src/desktop_app/face_widget.py` héberge `FaceWindow(hologram=True)` et le portrait d'ATLAS dans la même fenêtre Qt. La composition met la projection à gauche sur les écrans larges et sous le portrait sur les écrans étroits.
- `src/desktop_app/hologram_panel.py` contient `HologramPanel` (panneau découpé, transparence alpha, facettes, animation, affichage des requêtes/réponses) et `ProjectionBridge` (liaison animée). Rendu par **PyQt6 / QPainter**, sans nouvel environnement 3D ni dépendance supplémentaire.
- `src/desktop_app/app.py` instancie cette fenêtre via `FaceWindow(hologram=True)`, alimente l'aperçu par `LogSignals.new_log` et possède les commandes du service vocal et du chat.
- `src/desktop_app/desktop_assets/atlas_portrait.png` est le portrait de production. Le fichier n'a pas été modifié dans la dernière série de commits.
- `tests/test_hologram_panel.py` et `tests/test_atlas_portrait.py` contiennent déjà des scénarios de rendu, géométrie, transparence, affichage, états et préservation du portrait.
- L'interface actuelle utilise de **vrais pixels transparents et un masque polygonal**. En revanche, la réfraction, les reflets et la profondeur sont simulés en 2D ; aucun rendu optique 3D physique n'a été établi.

## 4. Derniers changements enregistrés le 29 octobre

Référence de départ avant les modifications : `ead6398ec5466eb8c1799b5d7fda166fefed3dca`.  
Dernier commit confirmé dans `develop-atlas` à l'écriture de cette fiche : `453f37abcca10a670789ead1a82dc214c4e209f4`.  
Le comparatif GitHub indique **quatre commits**, couvrant **quatre fichiers** :

| Commit | Fichier | Changement |
| --- | --- | --- |
| `f29a531b` | `tests/test_hologram_controls.py` | Quatre tests ajoutés pour les commandes, l'état vocal et les requêtes textuelles. Écrits avant l'implémentation, mais non exécutés. |
| `2af1680` | `src/desktop_app/hologram_panel.py` | Boutons Qt « ACTIVER / SUSPENDRE / REPRENDRE VOIX » et « ÉCHANGES », signaux de commande, accessibilité et remontée des demandes « Typed ». |
| `c1a412f` | `src/desktop_app/app.py` | Branchement des signaux holographiques sur les commandes existantes de démarrage, pause/reprise vocale et ouverture du chat. |
| `453f37ab` | `src/desktop_app/desktop_app.spec.md` | Documentation du comportement des nouvelles commandes et des états confirmés/en attente/inconnus. |

**Limite de la vérification :** commits et contenu des fichiers confirmés dans GitHub. Tests automatisés **non exécutés**. Aucun rendu sur le GTR7 Windows n'a été inspecté. Aucun résultat de fluidité, ergonomie ou performance ne doit être présenté comme validé. Les vérifications GitHub n'avaient aucun contrôle CI renseigné pour le dernier commit au moment de la consultation.

## 5. Points de vigilance techniques

1. **Nommage hérité.** L'application n'est pas encore purgée de `jarvis` ni de toutes les identités d'origine. Dans le dépôt consulté, des importations de `jarvis.activity` et un alias `JarvisSystemTray = ATLASSystemTray` subsistent. Le script Windows `scripts/run_desktop_app.bat` affiche toujours des messages d'origine et utilise `JARVIS_VOICE_DEBUG`. C'est un chantier ATLAS prioritaire à planifier avec tests de non-régression.
2. **Clics et gestes.** Le panneau auparavant transparent aux événements de souris accueille désormais deux vrais boutons. Vérifier qu'ils cliquent, que le déplacement global et le menu contextuel fonctionnent toujours, et que les zones découpées laissent passer les clics hors silhouette.
3. **Véritable état vocal.** La projection doit refléter l'état confirmé, sans annoncer « reprise » avant l'accusé de réception. Tester le démarrage, la pause, la reprise, l'indisponibilité, le délai d'attente et les processus arrêtés.
4. **Texte et confidentialité.** Les derniers échanges affichés viennent des journaux existants ; ne pas contourner les mécanismes de masquage des données. Tester les messages saisis, les messages parlés, les caractères spéciaux et les réponses multiline. Ne jamais interpréter le texte comme HTML.
5. **Écrans réduits.** Vérifier en particulier le mode compact, la visibilité des nouvelles commandes et des derniers messages, la disposition verticale, les écrans HiDPI et les dimensions réelles de l'écran du GTR7.
6. **Animations et performances.** Mesurer l'impact des minuteries `QTimer`, du `QPainter`, des masques natifs Windows et du passage entre états. Ne rajouter OpenGL, shaders ou dépendances que si un déficit mesuré le justifie.
7. **Écart artistique.** Les facettes Qt existantes ne prouvent pas à elles seules la « signature holographique premium » voulue ; le rendu visuel doit être évalué sur la fenêtre réellement exécutée avant tout nouveau changement lourd.

## 6. Procédure de reprise conseillée, dans l'ordre

### Étape A : relire et sécuriser

- Contrôler la branche `develop-atlas`, son dernier commit et l'absence de modifications inattendues. **Ne pas travailler sur `main`.**
- Comparer le contenu des quatre fichiers concernés et les instructions ATLAS propres au projet.
- Ne pas toucher à `src/desktop_app/desktop_assets/atlas_portrait.png` ni au rendu labial `FaceWidget`.

### Étape B : tests automatisés, puis lancement du GTR7

Depuis la racine du dépôt, dans l'environnement Python du projet et avec `PYTHONPATH` correctement configuré, exécuter notamment :

```powershell
python -m pytest -q tests/test_hologram_controls.py tests/test_hologram_panel.py tests/test_atlas_portrait.py
```

La commande ci-dessus est un **plan de test non encore exécuté**, pas un résultat. Ajouter les tests d'intégration Qt/voix pertinents si les premières vérifications passent.

Pour lancer l'interface sur le GTR7 Windows, le dépôt comporte actuellement le point d'entrée :

```powershell
.\scripts\run_desktop_app.bat
```

Ce script est **préexistant et n'a pas été exécuté dans cette session**. Il contient encore du vocabulaire et des noms d'environnement hérités à remplacer lors du travail de normalisation ATLAS. Vérifier l'environnement `.mamba_env` et les dépendances avant lancement. Le contrôle physique Windows exige l'exécution sur le mini-PC de l'utilisateur.

### Étape C : validation manuelle en conditions réelles

- Capturer la nouvelle fenêtre en fonctionnement, sans modifier ni déplacer artificiellement le robot.
- Contrôler les couleurs, contours irréguliers, transparence, contraste et lisibilité du panneau.
- Vérifier le lien visuel entre ATLAS et le panneau, les animations d'apparition et les états écoute / réflexion / réponse.
- Cliquer sur le contrôle vocal, puis sur « ÉCHANGES » ; confirmer les comportements réels.
- Vérifier déplacement de l'ensemble, clic droit, affichages réduits, absence de débordement et stabilité Windows.
- Constater l'utilisation CPU/RAM et les éventuels à-coups avant de juger la fluidité.

### Étape D : identité de code exclusivement ATLAS

Faire un audit ciblé de toutes les occurrences de l'ancien nom (sources, scripts, imports, tests, ressources, manifeste de compilation, documentation, configuration, environnement, chemins persistés et packaging). Identifier les références internes réellement renommables et les données historiques devant éventuellement conserver une migration. Corriger par sous-ensembles testables, sans remplacer aveuglément `jarvis` par `atlas` ni casser les modules, lancements Windows, sauvegardes ou installations existantes. La cible est **une application exclusivement ATLAS**. La priorité de conception est ATLAS, pas la compatibilité cosmétique avec l'ancien produit.

### Étape E : décision graphique et prochaine correction

Une fois la version fonctionnelle validée, comparer sa capture réelle à la demande : projection sculpturale, plexiglas premium, fusion lumineuse avec ATLAS. Identifier les écarts concrets, modifier au minimum les composants de projection nécessaires, compléter les tests et revalider.

## 7. Critères de fin de tâche

- [ ] Tests automatisés de l'hologramme et du portrait exécutés et réussis.
- [ ] Interface ATLAS lancée et inspectée sur le GTR7 Windows.
- [ ] Portrait, position et lèvres du robot visuellement inchangés.
- [ ] Boutons vocaux et échanges réellement fonctionnels.
- [ ] Tous les états vocaux et leur retour d'erreur correctement représentés.
- [ ] Contours non rectangulaires et pixels de transparence vérifiés visuellement.
- [ ] Affichage lisible et responsive à plusieurs résolutions, sans blocage de la souris.
- [ ] Fluidité et consommation de ressources vérifiées.
- [ ] Nommage ATLAS complet après audit et migration testée, aucune identité Jarvis dans le code final de production.
- [ ] Toute modification future limitée à `develop-atlas`, avec compte rendu fichiers / changements / justification / tests.

**Point de reprise immédiat :** vérifier la tête de `develop-atlas`, lancer les tests Qt ciblés puis la véritable application sur Windows avant toute nouvelle refonte. Ne pas déclarer les changements validés sans résultats. **Ne rien entreprendre automatiquement durant la nuit.**
