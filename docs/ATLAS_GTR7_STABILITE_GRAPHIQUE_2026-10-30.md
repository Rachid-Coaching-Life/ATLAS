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
