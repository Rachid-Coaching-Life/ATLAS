# ATLAS — Stabilisation graphique GTR7 (30 octobre 2026)

## Contexte vérifié

- L'application a affiché le vrai portrait ATLAS accompagné d'une projection Qt. La projection obtenue reste très différente du concept holographique approuvé : rendu trop plat, faibles contrastes, détails insuffisants, typographie minuscule.
- Le système Windows du GTR7 a subi des arrêts inattendus. Le journal fourni mentionne Kernel-Power 41 autour de 07:39:54 et 08:00:15 ; les événements 6008 récapitulent des arrêts précédents non prévus. **Aucune preuve ne relie encore ces arrêts au rendu Qt, au pilote AMD ou à ATLAS.**
- L'utilisateur rapporte qu'un autre logiciel (OnlyOffice) devenait stable après désactivation de son accélération graphique. C'est un contexte pertinent, **pas une preuve de mécanisme commun**.
- 27 tests de projection/portrait/commandes avaient réussi dans la venv Windows Python 3.11.9, **avant les modifications de stabilisation décrites ci-dessous**.
- Le portrait local `src/desktop_app/desktop_assets/atlas_portrait.png` a été signalé modifié (`M`) et ne doit être ni restauré ni remplacé.

## Correction minimale sur `develop-atlas`

- `src/desktop_app/hologram_panel.py` : une projection « asleep » ou « idle » ne redessine plus continuellement ; en état actif, limite la minuterie de projection à 250 ms (4 rafraîchissements/s), et celle du pont lumineux également à 250 ms. Les transitions d'état continuent à déclencher immédiatement un rendu. Le portrait et son animation ne changent pas.
- `tests/test_hologram_panel.py` : deux nouveaux tests de cycle de vie des minuteries et de changement d'état. **Non exécutés sur GTR7 à l'écriture.**
- `scripts/preview_atlas_hologram_offscreen.py` : génère une capture PNG de la vraie projection Qt à l'aide du moteur offscreen, sans lancer de services vocaux, de modèles, de system tray ou de fenêtre native. C'est un outil de prévisualisation et non un test de stabilité de Windows.

Les effets de transparence, le masque natif Windows et l'animation du portrait subsistent : aucun correctif définitif de crash n'est revendiqué.

## Validation progressive — sans lancer immédiatement l'application complète

Dans PowerShell depuis la racine du dépôt ATLAS :

```powershell
git switch develop-atlas
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_hologram_controls.py tests/test_hologram_panel.py tests/test_atlas_portrait.py
```

Si les tests réussissent, réaliser une **prévisualisation hors écran uniquement** :

```powershell
.\.venv\Scripts\python.exe scripts\preview_atlas_hologram_offscreen.py
```

Le script indique le chemin du PNG dans le dossier temporaire Windows. Contrôler ensuite le rendu sans démarrer ATLAS en mode interactif. Le lancement complet reste conditionné à un protocole d'essai prudent et à une surveillance du GTR7.

## Décisions de développement

1. Ne pas modifier `main`, le portrait, la géométrie faciale ou l'animation labiale.
2. Ne pas ajouter de moteur 3D, shaders, dépendances lourdes ou promesses de stabilité sans mesures.
3. Favoriser les tracés Qt simples, la mise en cache des éléments statiques et les rafraîchissements déclenchés par événements.
4. Sur Windows, Qt Widgets utilise habituellement un chemin de peinture raster ; l'accélération du compositeur Windows et les composants QtWebEngine éventuels restent distincts. Ne pas assimiler automatiquement cette application à OnlyOffice.
5. Après les nouveaux tests, produire une capture hors écran, puis examiner le dessin et les zones de commande pour améliorer la fidélité esthétique sans relancer une charge lourde.
6. Conserver un relevé des événements Windows et utiliser la vraie application uniquement après les étapes précédentes, avec une validation manuelle explicite. Un nouvel arrêt du système interdit de multiplier les essais.

## À faire

- [ ] Exécuter tous les tests après stabilisation sur Windows.
- [ ] Exécuter la prévisualisation hors écran et contrôler l'apparence réelle de l'hologramme.
- [ ] Réaliser une vraie refonte du panneau selon la référence approuvée, en gardant les limites de charge.
- [ ] Inspecter les performances CPU/GPU, la transparence et le comportement Windows avant de conclure à la stabilité.
- [ ] Auditer séparément les références héritées de l'ancienne identité dans le code, scripts et documentation, sans remplacement aveugle.


## Incident supplémentaire et diagnostic révisé (11 h 33, 30 octobre 2026)

L'utilisateur a confirmé un nouvel arrêt brutal de l'ordinateur lors de l'affichage
d'ATLAS. Le journal System contient trois événements Kernel-Power 41 datés
07:39:54, 08:00:15 et 11:33:27 ; chacun porte `BugcheckCode=0` et
`PowerButtonTimestamp=0`.

**Interprétation :** un arrêt n'a pas été journalisé normalement. Cela ne
prouve ni une surcharge GPU, ni une erreur du code ATLAS. Une perte
d'alimentation, un pilote bloqué ou un arrêt trop rapide pour écrire les données
restent possibles. La documentation Microsoft recommande, dans cette
configuration, de rechercher aussi `volmgr` 46, des erreurs WHEA et les
événements de pilote graphique.

**Aucun nouvel essai de lancement complet ne doit être demandé** tant que
les indices d'alimentation et de système n'ont pas été examinés.

### Interrupteur de diagnostic (à ne pas activer pour le moment)

Ajout dans `src/desktop_app/app.py` :

- Sans variable, l'application reste exactement en mode holographique habituel.
- `ATLAS_DIAGNOSTIC_NO_HOLOGRAM=1` remplace la projection combinée par
  `FaceWindow(hologram=False)` et conserve le portrait identique.
- Les connexions des boutons holographiques sont conditionnées à leur
  existence pour éviter une erreur lorsque le panneau est absent.
- **Ce n'est pas un mode sécurisé garanti** : la fenêtre du portrait reste
  translucide et animée, Qt/Windows restent utilisés, et le démarrage vocal
  automatique ne change pas. Ce mode servira à une comparaison ultérieure
  **seulement après vérification des causes de coupure**.

Test ajouté à `tests/test_hologram_controls.py` pour vérifier le défaut
holographique et l'absence de panneau en mode diagnostic. **Non exécuté au
moment de l'enregistrement.** La dernière série de tests communiquée par
l'utilisateur était de 39 réussites, antérieure à cet ajout.

### Lecture sans risque des journaux Windows

Depuis PowerShell, sans lancer ATLAS :

```powershell
Get-WinEvent -FilterHashtable @{
    LogName='System'
    StartTime=[datetime]'2026-10-30 11:00'
    EndTime=[datetime]'2026-10-30 11:40'
} -ErrorAction SilentlyContinue |
Where-Object {
    $_.ProviderName -match 'WHEA-Logger|Display|volmgr|amdw|Kernel-Power' -or
    $_.Id -in 1001,4101,46
} |
Select-Object TimeCreated,Id,ProviderName,Message | Format-List
```

Ne pas assimiler tous les événements portant l'identifiant 18 à des erreurs
matérielles : vérifier le champ `ProviderName`.


## Instrumentation sans charge (30 octobre 2026)

L'utilisateur souhaite avancer et distinguer la panne matérielle d'une erreur
graphique. Le PC est pour le moment alimenté en USB-C par un bloc annoncé
140 W ; la puissance effectivement négociée est **inconnue**. Des
spécifications publiées pour le GTR7 indiquent 100 W USB-PD sur les ports
USB4, et le support Beelink cite une mise à jour du BIOS améliorant la
compatibilité de l'alimentation PD ; **ne pas mettre le BIOS à jour dans
le cadre de ce diagnostic**.

Sources :
- https://www.hwinfo.com/download/ (éditeur officiel REALiX)
- https://www.hwinfo.com/version-history/
- https://www.notebookcheck.net/Beelink-GTR7-and-GTR7-Pro-now-available-with-AMD-Ryzen-7-7840HS-and-Ryzen-9-7940HS.720457.0.html
- https://www.bee-link.com.cn/cms/support/driverhardware?product_id=117
- https://learn.microsoft.com/fr-fr/troubleshoot/windows-client/performance/event-id-41-restart

### Premier relevé recommandé

1. Télécharger HWiNFO64 depuis **hwinfo.com**, de préférence en
   version portable. Il peut charger un pilote signé pour lire les
   capteurs ; tout ajout logiciel peut présenter des risques.
2. Ouvrir **Sensors-only** et repérer si disponibles : température
   CPU/Tctl/Tdie, température GPU, CPU package power, GPU power,
   charge CPU/GPU, fréquence, indicateurs de throttling.
3. Activer le **CSV sensor logging** (icône disque) dans un dossier
   local hors du dépôt ; utiliser un intervalle modéré (par exemple
   2000-5000 ms) et commencer uniquement au repos, sans lancer ATLAS.
4. Enregistrer une courte session normale, puis arrêter l'enregistrement.
   Les données ne donnent pas la puissance réelle du contrat USB-PD.
   En cas de coupure brutale, les dernières lignes peuvent manquer.
5. Éviter stress tests CPU/GPU, OCCT/FurMark, changements de TDP/BIOS,
   ou répétitions volontaires de l'extinction avec l'alimentation actuelle.

### Mesures Windows passives, sans logiciel supplémentaire

Dans PowerShell :

```powershell
Get-CimInstance Win32_VideoController |
  Select-Object Name, DriverVersion, DriverDate |
  Format-List
Get-CimInstance Win32_BIOS |
  Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate |
  Format-List
Get-CimInstance Win32_ComputerSystem |
  Select-Object Manufacturer, Model |
  Format-List
```

Les résultats permettent de vérifier la configuration de départ. Ne pas
faire de mise à jour du pilote AMD sur la seule foi du code 41.

### Diagnostic logiciel déjà préparé, ne pas utiliser comme stress test

Sur `develop-atlas`, dans `src/desktop_app/app.py` :

- `ATLAS_DIAGNOSTIC_NO_HOLOGRAM=1` : portrait seul ;
- `ATLAS_DIAGNOSTIC_NO_AUTOSTART=1` : pas de démarrage vocal/IA
  automatique (ajouté séparément) ;
- par défaut, aucune des deux variables n'est active.

Ces options permettent de distinguer visuel / audio lors d'essais
**seulement lorsque l'alimentation est reconnue stable et l'essai jugé
acceptable**. Elles ne garantissent pas la sécurité de l'essai, car
le moteur Qt, la fenêtre translucide et certaines animations restent actifs.

Test de non-régression ajouté dans
`tests/test_hologram_controls.py`. Les tests n'ont pas encore été
exécutés après l'ajout ; aucun gain de stabilité matérielle n'est revendiqué.


## Résultats du CSV HWiNFO et relevé des processus (30 octobre 2026)

Source locale examinée : `GTR7-test-COPIE.CSV`, 6 328 lignes de mesures,
274 colonnes, échantillonnées entre 08:01:42.892 et 11:32:42.766.
L'événement Kernel-Power 41 à 11:33:27 est enregistré par Windows
après l'arrêt anormal, potentiellement au redémarrage : **ne pas déduire
de ces deux horaires une coupure exactement 45 secondes après la mesure**.

**Deux compteurs HWiNFO différents portent quasiment le même nom :**
`Utilisation totale du processeur [%]` et la seconde colonne de même
intitulé (`.1` après import pandas). Dernier point : 99,3 % contre
59,4 % respectivement. Ne pas rapporter uniquement 99,3 % comme une
mesure indiscutable de l'occupation CPU. La température du CPU à ce
point est de 46,8 °C et la consommation mesurée du CPU de 16,712 W.
Température GPU : 45,5 °C. La température capteur `SPD Hub` est
69,8 °C, sans prouver la température des puces DDR5. Aucun drapeau
PROCHOT/HTC dans le journal, mais les capteurs pourraient manquer
l'instant d'un arrêt électrique.

Après redémarrage, un échantillon PowerShell de 5 secondes donne :
Zoom 5,8 % CPU, DWM 0,7 %, Camera Hub 0,5 %, System 0,5 %,
HWiNFO64 0,5 %, autres inférieurs à 0,5 %. **Ce relevé ne permet
pas d'attribuer la charge CPU avant la coupure à Zoom ni à ATLAS**.

**Suite conseillée sans stress matériel :** ouvrir le Moniteur de
fiabilité (`perfmon /rel`, commande Microsoft documentée) et
examiner les incidents et leurs détails techniques du 30 octobre.
Conserver le mode diagnostic sans démarrage vocal/IA pour des
essais ultérieurs si l'alimentation est confirmée compatible et stable.

Référence sur les écarts entre compteurs CPU :
https://www.hwinfo.com/forum/threads/cpu-usage-question.4162/
Référence Moniteur de fiabilité :
https://learn.microsoft.com/fr-be/windows-server/administration/windows-commands/perfmon


## 30 octobre — Profilage Qt hors écran et mode holographique allégé

Après l'analyse du pilote AMD et du journal Kernel-PnP (quatre événements
anciens, du 25 août et 4 septembre ; aucun événement du 30 octobre dans
cette vue), les extinctions ne sont toujours **pas attribuables avec
certitude au rendu**. Le GTR7 est toujours alimenté par USB-C 140 W
nominal, avec négociation électrique inconnue.

Audit du code :
- Le panneau et le pont utilisent un `QTimer` actif à 250 ms (4 Hz).
- Le portrait utilise séparément un `QTimer` à 33 ms pendant certaines
  activités, 50 ms en état idle, et 250 ms en repos `asleep`.
- Chaque rendu du panneau produit trois dégradés radiaux, des reflets,
  un fin quadrillage, des détails électroniques et des particules.
  Leur existence est vérifiée ; leur coût réel sur le GTR7 **n'est pas
  encore mesuré**. Le coût DWM/Windows reste en dehors du raster Qt.

Correction isolée :
- `src/desktop_app/hologram_panel.py` : variable d'environnement
  facultative `ATLAS_HOLOGRAM_LOW_EFFECTS=1` ; supprime uniquement
  dégradés radiaux décoratifs, facettes lumineuses, quadrillage,
  microdétails et particules ; panneau/pont à 500 ms pendant l'activité.
  Maintient îlots, surfaces de texte, commandes vocales et échanges,
  émetteur de liaison. Ne touche ni portrait, ni dimensions, ni GPU API.
- **Sans** cette variable, l'hologramme reste strictement dans
  le mode de dessin et à 250 ms comme avant.
- `scripts/profile_atlas_hologram_offscreen.py` : mesure
  `QWidget.render(QImage)` pour panneau normal/allégé (idle/listening),
  pont normal/allégé et portrait (idle/speaking), puis exporte
  `%TEMP%\\ATLAS_offscreen_render_profile.json`.
  Utilise `QT_QPA_PLATFORM=offscreen`, pas de démarrage du démon vocal,
  pas de nouvelle fenêtre native ni d'appel OpenGL.

Reproduction sur le GTR7 **sans lancer ATLAS interactif** :

```powershell
cd C:\\Users\\cheha\\ATLAS
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\\src"
.\\.venv\\Scripts\\python.exe -m pytest -q tests/test_hologram_controls.py tests/test_hologram_panel.py tests/test_atlas_portrait.py
.\\.venv\\Scripts\\python.exe scripts\\profile_atlas_hologram_offscreen.py
Get-Content "$env:TEMP\\ATLAS_offscreen_render_profile.json"
```

Le profil fournit des durées de **raster CPU hors écran par image**. Elles
ne mesurent pas les watts, la négociation USB-PD, le GPU, la consommation
du compositeur Windows ni la stabilité d'une fenêtre native. Une
différence de millisecondes n'établit donc pas une cause des coupures.
Les résultats de benchmark et tests sur Windows restent à confirmer
après ce commit.


## Mesure reçue du GTR7 — rendu Qt normal / allégé

Après mise à jour jusqu'au commit `d06192b`, les tests demandés ont réussi :
**44 passed in 5.48s**.

Commande utilisée :
`python scripts/profile_atlas_hologram_offscreen.py --samples 8 --warmup 2`.

| Composant (médiane) | Normal | Allégé | Observation |
|---|---:|---:|---|
| HUD idle | 9,778 ms | 5,504 ms | −43,7 % |
| HUD listening | 9,704 ms | 5,763 ms | −40,6 % |
| Pont idle | 0,289 ms | 0,288 ms | Quasiment identique |
| Pont listening | 0,395 ms | 0,326 ms | Gain modeste |
| Portrait idle | 0,221 ms | sans objet | Pas modifié |
| Portrait speaking | 0,391 ms | sans objet | Pas modifié |

**Calcul de charge de dessin périodique (modèle, pas mesure réelle
Windows) :** au cours de l'écoute, HUD normal :
`9,704 ms × 4 Hz = 38,816 ms CPU/seconde` ; HUD allégé :
`5,763 ms × 2 Hz = 11,526 ms CPU/seconde` ; réduction
théorique de 70,3 % du temps de rendu périodique du panneau.
Les rafraîchissements déclenchés par d'autres événements Qt,
le compositor DWM, la charge graphique AMD, les watts et les pointes
électriques **ne sont pas mesurés**.

**Décision :** conserver le portrait tel quel et le mode normal par
défaut ; maintenir le mode allégé facultatif tant que sa lisibilité
sur fond réel n'a pas été évaluée. Pas d'essai de l'application complète
avec l'alimentation USB-C actuelle.

### Validation visuelle sans écran natif

```powershell
$env:ATLAS_HOLOGRAM_LOW_EFFECTS = "1"
.\\.venv\\Scripts\\python.exe scripts\\preview_atlas_hologram_offscreen.py
start "$env:TEMP\\ATLAS_hologram_sur_fond.png"
Remove-Item Env:ATLAS_HOLOGRAM_LOW_EFFECTS
```

Ces commandes ne lancent pas le démon vocal ; elles produisent une
image de la projection uniquement. Elles ne prouvent pas la stabilité
matérielle de Windows.


## Validation visuelle du mode allégé sur plusieurs fonds

L'utilisateur a fourni la vue hors écran `ATLAS_hologram_sur_fond.png`
du **mode allégé**. Elle confirme que sur un fond sombre :
- les deux cartes de dialogue restent lisibles ;
- la plaque titre, la télémétrie, les commandes et l'émetteur sont visibles ;
- l'effet 3D est plus discret qu'un véritable hologramme volumique.

Cela **ne valide pas la lisibilité sur fond clair** et ne constitue
aucune mesure de consommation GPU ou électrique.

Pour éviter une retouche prématurée du moteur de dessin, le script
`scripts/preview_atlas_hologram_offscreen.py` génère désormais
une troisième image sur fond clair simulé
(`%TEMP%\ATLAS_hologram_sur_fond_clair.png`), en superposant
la **même** image Qt transparente que la vue sombre. Aucun changement
du panneau normal ni du portrait ; aucune animation supplémentaire.

Commande (PowerShell, depuis le dépôt) :

```powershell
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
$env:ATLAS_HOLOGRAM_LOW_EFFECTS = "1"
.\.venv\Scripts\python.exe scripts\preview_atlas_hologram_offscreen.py
Remove-Item Env:ATLAS_HOLOGRAM_LOW_EFFECTS
start "$env:TEMP\ATLAS_hologram_sur_fond_clair.png"
```

Un test d'export du nouveau PNG et de sa géométrie a été ajouté dans
`tests/test_hologram_panel.py`. **À exécuter sur le GTR7**.
La version normale est toujours le réglage par défaut et les coupures
d'alimentation USB-PD restent non résolues.


## Correction du lancement des tests en mode « allégé »

Lors du contrôle du script sur fond clair, `tests/test_hologram_panel.py`
a terminé par `26 passed, 2 failed`. Les deux assertions qui ont
échoué exigeaient `panel._timer.interval() == 250` mais obtenaient
`500`. La variable PowerShell `ATLAS_HOLOGRAM_LOW_EFFECTS=1`
était encore définie lors de l'exécution de pytest, avant son
`Remove-Item Env:...` ultérieur. Cette variable active volontairement
un intervalle de 500 ms : ce n'est donc **pas une preuve de régression
du rendu**.

Les tests `test_orbital_glass_emitter_respects_cutouts_and_idles_without_repaint`
et `test_hologram_islands_keep_real_controls_and_compact_fallback`
suppriment maintenant cette variable via `monkeypatch.delenv(...)`
avant la création des composants, pour tester explicitement le mode
normal. `monkeypatch` restaure automatiquement l'environnement après
chaque test.

Les 2 tests corrigés **n'ont pas encore été réexécutés sur Windows**
au moment de ce commit. La vue sur fond clair a bien été générée
par le script ; sa lisibilité reste à évaluer à partir de la capture.


## Étape suivante — calque holographique statique en cache CPU

Objectif : récupérer une partie de la profondeur lumineuse du mode normal
sans redessiner toutes les lumières et les microcircuits à chaque image.
Le portrait et sa fréquence d'animation restent **intouchés**.

Implémentation expérimentale sur `develop-atlas` :
- `src/desktop_app/hologram_panel.py` ajoute
  `ATLAS_HOLOGRAM_CACHED_EFFECTS=1` (désactivé par défaut).
- Les reflets, dégradés radiaux et microcircuits **déjà présents** sont
  calculés une fois dans un `QImage` prémultiplié, transparent et découpé
  selon la même silhouette. Le calque est réutilisé au prochain
  `paintEvent`, et reconstruit si largeur, hauteur ou échelle DPI change.
- La surface ne dépasse pas les dimensions du panneau ; à 505x330 et
  DPR 1, buffer d'environ 0,64 Mio. Aucun shader, OpenGL, moteur 3D,
  ressource téléchargée, boucle d'animation, modification de portrait.
- En combinant `ATLAS_HOLOGRAM_LOW_EFFECTS=1` et la nouvelle variable,
  la lumière statique est restaurée, mais les ornements dynamiques
  allégés et le timer à 500 ms sont conservés.
- Sans les variables, mode d'origine préservé.

Le banc `scripts/profile_atlas_hologram_offscreen.py` compare désormais
trois profils : `normal` (4 Hz), `alleger` (2 Hz, sans cette couche)
et `hybride` (2 Hz, couche en cache) ; il mesure toujours uniquement
`QWidget.render(QImage)` sans démarrer l'application.
Deux tests contrôlent cache / redimensionnement / commandes et opt-in.
**Les performances de cette nouvelle méthode ne sont pas encore
mesurées sur le GTR7**, et ne doivent pas être annoncées comme acquises.

Commandes de validation, sans fenêtre native ni moteur vocal :

```powershell
cd C:\Users\cheha\ATLAS
git pull --ff-only origin develop-atlas
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q tests/test_hologram_controls.py tests/test_hologram_panel.py tests/test_atlas_portrait.py
.\.venv\Scripts\python.exe scripts\profile_atlas_hologram_offscreen.py --samples 8 --warmup 2
$env:ATLAS_HOLOGRAM_LOW_EFFECTS = "1"
$env:ATLAS_HOLOGRAM_CACHED_EFFECTS = "1"
.\.venv\Scripts\python.exe scripts\preview_atlas_hologram_offscreen.py
start "$env:TEMP\ATLAS_hologram_sur_fond_clair.png"
Remove-Item Env:ATLAS_HOLOGRAM_CACHED_EFFECTS -ErrorAction SilentlyContinue
Remove-Item Env:ATLAS_HOLOGRAM_LOW_EFFECTS -ErrorAction SilentlyContinue
```

Comparer d'abord les temps réels et la lisibilité du mode hybride
avant de modifier le réglage par défaut. **Ne pas lancer l'application
complète avec l'alimentation USB-C actuelle.**


## Mesure réelle du calque hybride et correction des rails de cartes

Mesures reçues sur GTR7 (`--samples 8 --warmup 2`) après commit
`4899c7f` : **46 tests réussis en 4,69 s**.

| Élément | Normal | Allégé | Hybride |
|---|---:|---:|---:|
| HUD idle (médiane) | 9,218 ms | 5,273 ms | 5,595 ms |
| HUD listening (médiane) | 9,430 ms | 5,743 ms | 6,379 ms |
| Pont listening (médiane) | 0,287 ms | 0,338 ms | 0,309 ms |

Portrait inchangé : 0,215 ms au repos, 0,413 ms en parole.
L'hybride gagne 32,4 % de temps CPU de peinture du panneau en écoute
par rapport au mode normal, mais coûte 11,1 % de plus que l'allégé.
Ces statistiques à 8 échantillons par état ne constituent pas une
mesure de consommation du GPU ou de stabilité électrique ; le mode
hybride reste **facultatif** et le réglage normal n'est pas modifié.

Capture fournie `ATLAS_hologram_sur_fond_clair.png` en hybride :
la lecture des cartes est correcte, mais le verre reste peu volumique
et certaines lignes lumineuses traversent les titres de section.
Un problème précis du code a été confirmé : `_glass_card`
soustrayait toujours 15 px à `label.geometry().top()`, sans tenir
compte de la hauteur et de l'espacement du titre `RÉPONSE` /
`DERNIÈRE DEMANDE`. Correction minimale dans
`src/desktop_app/hologram_panel.py` : chaque bordure supérieure est
désormais positionnée sous la légende Qt réelle via
`_glass_card_top`, sans déplacement du texte ni du portrait.
Test de géométrie ajouté pour les tailles 505×330 et 210×205.

**Ce nouveau test et la correction ne sont pas encore exécutés
sur Windows au moment de ce commit.** Avant de poursuivre la
complexité visuelle, vérifier lisibilité, non-régression et coût
du rendu, uniquement hors écran avec l'alimentation USB-C actuelle.


## 30 octobre — Contrôle visuel après correction des légendes

L'utilisateur a fourni une nouvelle image `ATLAS_hologram_sur_fond_clair.png`
après la correction du positionnement des rails des cartes. Les
titres « DERNIÈRE DEMANDE » et « RÉPONSE » ne sont plus traversés
par leur bord supérieur dans cette capture. Cette vérification est
**visuelle uniquement** : le message ne contient pas le résultat du
nouveau test de géométrie.

La lecture reste suffisante sur le fond clair simulé, mais les îlots
demeurent assez plats comparés à la référence artistique ATLAS.
Une retouche **minimale et facultative** a donc été apportée uniquement
à `src/desktop_app/hologram_panel.py` : trois fins traits forment une
lame de verre décalée derrière chaque carte. L'effet est activé
seulement si `ATLAS_HOLOGRAM_CACHED_EFFECTS=1` ET
`ATLAS_HOLOGRAM_LOW_EFFECTS=1`, sur panneau large (>=390 px).
Le mode normal, l'allégé simple, le portrait et les minuteries ne
changent pas. Il n'y a ni nouvelle image GPU, ni filtre flou, ni
nouvelle surface, ni moteur graphique.

Un test compare le bord translucide d'une même carte avec et sans
la nouvelle lame et vérifie la position du titre. **Le test et le coût
du rendu doivent encore être vérifiés sur Windows.** Si le surcoût
dépasse le bénéfice perçu, revenir à la version hybride mesurée
(`4899c7f`) ou supprimer les trois traits, sans toucher au portrait.

Avant tout lancement complet, la compatibilité et la stabilité
de l'alimentation USB-C du GTR7 restent à confirmer.


## Résultats reçus — 48 tests et profil CPU hors écran

Sur la branche `develop-atlas` au commit `c531c4f`, l'utilisateur a
obtenu **48 passed in 5.16s** sur les trois suites de tests Qt.

Mesures (`--samples 8 --warmup 2`), médianes par rendu :

| Composant | Normal | Allégé | Hybride |
|---|---:|---:|---:|
| HUD idle | 10,354 ms | 5,890 ms | 6,171 ms |
| HUD listening | 10,463 ms | 6,113 ms | 6,790 ms |
| Pont idle | 0,310 ms | 0,282 ms | 0,381 ms |
| Pont listening | 0,278 ms | 0,302 ms | 0,351 ms |

Portrait : **0,243 ms** idle et **0,455 ms** speaking, inchangé.

Comparaison à conditions similaires **dans le même relevé** :
- hybride en écoute : 35,1 % de temps de dessin en moins que normal ;
- allégé en écoute : 41,6 % en moins que normal ;
- hybride en écoute : 11,1 % de plus que l'allégé.

La mesure précédente donnait 6,379 ms en hybride listening contre
6,790 ms ici, mais les trois modes ont varié entre sessions ; **ne pas
attribuer cette variation au petit ajout des trois traits** sans essai
A/B contrôlé. Sur la prévisualisation claire, ces traits apportent une
profondeur peu perceptible, donc aucune raison de multiplier ces
ornements. L'architecture hybride reste expérimentale, activée
seulement à la demande. Le mode normal n'est pas changé.

**Décision :** arrêter les micro-retouches de traits, conserver le
portrait, passer à un changement de composition réellement visible
avec comparaison des rendus sur fonds clair/sombre. Contrôler la durée
de rendu et les tests après chaque changement. La charge DWM/GPU,
la puissance réelle de l'USB-C et la cause des extinctions restent
non mesurées ; ne pas lancer l'interface interactive complète avec
l'alimentation actuelle.
