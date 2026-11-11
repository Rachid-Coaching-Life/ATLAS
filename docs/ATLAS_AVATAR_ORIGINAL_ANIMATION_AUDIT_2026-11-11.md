# ATLAS — audit bloquant de l'avatar et contrat d'animation

**Date :** 11 novembre 2026  
**Statut :** diagnostic établi ; correction **non réalisée** ; essais GTR7 **non réalisés**.  
**Cible :** l'avatar d'origine validé par le propriétaire, inchangé visuellement, mais vivant et réellement articulé.

## Constats vérifiés dans le dépôt

1. `src/desktop_app/face_widget.py` utilise par défaut `FaceWidget(portrait=True)` et charge `desktop_assets/atlas_portrait.png`. Le rendu courant utilise `QPainter.drawPixmap(...)`, pas un modèle animé.
2. Les méthodes `_paint_portrait_blink` et `_paint_portrait_mouth` superposent des tracés 2D à cette image. **Ce n'est pas un maillage facetté, un rig ni un modèle 3D**.
3. `_update_blink` désactive les clignements lorsque `AtlasState.ASLEEP`; les autres états attendent une fenêtre de 4,5 à 7,5 secondes puis un événement de 0,28 seconde. L'absence de mouvement constatée par l'utilisateur est donc cohérente avec une limite du code, mais sa cause précise sur GTR7 n'a pas été reproduite.
4. `src/atlas/output/lip_sync.py` transporte les niveaux RMS PCM de Piper toutes les 40 ms ; le module signale lui-même l'absence de phonèmes ou de visèmes. Dans `face_widget.py`, la bouche peut rester fermée si `SPEAKING` n'est pas observé ou si aucun signal de lecture n'est disponible.
5. Le portrait PNG existe dans la branche depuis le commit `0587e094` du 29/10/2026. Son blob `68b4bccaf8586e3ace3db4e3e42b8b4d8aa8825f` est **identique** entre `develop-atlas` et la branche `chatgpt/atlas-installer-safety`. La migration Python n'a donc pas remplacé ce fichier.
6. L'historique situe le changement d'architecture visuelle le **29/10/2026**, commit `f66bc5aca4` (PNG par défaut), puis `6decd8a98a` (contours des lèvres), `7b5bc28279` le 30/10/2026 (contours des paupières). Il faut comparer l'image actuellement affichée à la version d'ATLAS expressément validée pour établir le désaccord visuel exact.
7. Inventaire de l'arbre versionné : **aucun fichier de modèle `.glb`, `.gltf`, `.fbx`, `.vrm`, `.obj`, `.blend` ou maillage animé équivalent**. Une « véritable transformation » n'est pas encore présente.

## Exigences non négociables

- **Identité d'origine préservée** : même robot, visage, proportions, détails mécaniques, couleurs, implantation et apparence au repos. Ne pas substituer un dessin, un portrait nouvellement généré ou l'ancien masque géométrique.
- **Personnage vivant** : animation corporelle/tête et expressions fines coordonnées au contexte, clignements naturels au repos **même sans réponse audio**, mouvements d'yeux/paupières cohérents.
- **Parole réelle** : articulation de la mâchoire et des lèvres **dans la géométrie du personnage**, alignée sur la lecture de la voix locale. Le niveau sonore RMS seul ne garantit pas les visèmes. Le mouvement doit s'arrêter lors d'une interruption ou de l'arrêt du TTS.
- **Aucune superposition simpliste** d'un trait sombre ou d'une forme qui cache les lèvres/yeux originaux ; il faut un modèle riggé/maillé ou une animation faciale équivalente **réellement déformable**.
- **Interface gauche inchangée** dans ce chantier ; ne pas modifier les outils, la lecture PDF, la configuration des modèles, les règles de sécurité, le dépôt Révision-TSSR ni les branches `main` et `develop-atlas`.
- **Exécution locale Windows GTR7** ; aucune dépendance ou service externe non justifiés.

## Déroulement imposé

### A. Fidélité visuelle (avant toute transformation)

- Obtenir et archiver dans la branche d'étude une **référence visuelle exacte** de l'ATLAS validé (capture ou modèle source) ; comparer aux pixels affichés par `atlas_portrait.png` et vérifier si le problème provient de l'asset lui-même, d'un recadrage ou d'un changement de moteur de rendu.
- Ne pas activer un autre portrait par défaut sans validation visuelle.

### B. Inventaire des sources d'animation

- Chercher les sources/articulations/masks existantes, sans en inventer.
- Si seuls les pixels PNG sont disponibles, reconnaître que le rig est à construire : définir un format léger de maillage/points de contrôle + couches oculaires/mâchoire capable de préserver l'identité **sans modification destructrice de l'asset original**.
- Faire un prototype isolé et réversible, pas un remaniement de l'application.

### C. Chaîne de parole et états

- Auditer `AtlasState.SPEAKING`, les durées de TTS, les interruptions et le signal `lip_sync.py`.
- Synchroniser les formes articulatoires avec la voix réelle (visèmes si disponibles), sans utiliser une oscillation arbitraire comme seule preuve.
- Assurer le clignement et les micro-expressions au repos sans simuler une réponse vocale.

### D. Tests et validation

- **Test de rendu visuel** : correspondance de la pose neutre à la référence ; aucune substitution du robot ni du panneau.
- **Test vidéo/animation** : séquences repos, écoute, réflexion, réponse, interruption ; clignement autonome et mâchoire réellement déformée.
- **Test technique** : framerate stable, CPU/GPU et mémoire mesurés sur le GTR7, synchronisation audio/animation, maintien des performances de l'assistant.
- **Test intégré** : installation Windows, activation vocale, vraie réponse audible, puis comparaison de l'animation observée.
- Ne pas annoncer « corrigé » sur la base d'un test de démarrage, d'une animation 2D superposée ou de tests qui n'observent pas réellement les frames.

## État d'avancement

| Étape | État |
| --- | --- |
| Localisation de l'introduction du PNG fixe et du faux mouvement | **Audit vérifié** |
| Intégrité du fichier `atlas_portrait.png` pendant la migration | **Vérifiée** (même blob Git) |
| Correspondance à la référence visuelle approuvée | **Non vérifiée** |
| Modèle animé réellement riggé dans le dépôt | **Absent** |
| Animation du visage intégrée et fidèle | **Non implémentée** |
| Test vidéo et validation sur GTR7 | **Non réalisés** |

**Décision :** l'avatar est un blocage produit. Ne pas présenter ATLAS comme complet tant que cette exigence n'est pas remplie.
