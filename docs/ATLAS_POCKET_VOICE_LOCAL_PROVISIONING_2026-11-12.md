# ATLAS — Profil vocal Pocket TTS, préparation privée sur Windows

Statut : script et tests synthétiques préparés ; export de la véritable voix personnelle sur GTR7 non encore exécuté.

## Preuves existantes

Sur GitHub Actions Windows, la PR #37 a confirmé le binaire officiel Pocket TTS Rust 3.3.0 (release du dépôt Kyutai v4.0.1), la génération française avec la voix publique Estelle, puis une nouvelle génération avec endpoint HF bloqué. Les tests du pont de synthèse et des interruptions ont réussi sur le même run. Ces résultats ne prouvent pas le clonage de la voix personnelle ni la vitesse réelle sur GTR7.

## Une seule procédure prévue

Le script scripts/prepare_pocket_voice.py utilise un seul WAV de référence de 5 à 30 secondes et crée un nouveau profil safetensors localement. La référence personnelle candidate de 15 secondes est conservée hors dépôt. Il faut d'abord disposer du binaire officiel pocket-tts.exe et des chemins privés existants sur le GTR7. Le script ne copie aucune donnée vers GitHub.

Archive officielle : pocket-tts-3.3.0-x86_64-pc-windows-msvc.zip.
Empreinte SHA-256 : 98753041f2e65744b989776f87bccb93f1f574a08afe1890c5427ec94cd6309c.

L'exécutable extrait de cette archive a le SHA-256
`813cabfc2f8fc7a4e5310deda6025426b3164610dd9f3c3098a6078e5cc1895a`.
Les deux points d'entrée vérifient cette empreinte avant toute exécution,
y compris `--version`. Un binaire existant inconnu est refusé et conservé.
Le lanceur vérifie le fichier préparatoire avant sa publication atomique sans
écrasement. Sous Windows, le déplacement atomique retire simultanément le nom
préparatoire ; une erreur de validation ne crée pas de moteur installé.

Exemple de commande PowerShell (CHEMIN_PRIVE doit être remplacé par un chemin réellement existant sur le GTR7) :

~~~powershell
python scripts/prepare_pocket_voice.py --binary "C:\CHEMIN_PRIVE\pocket-tts.exe" --reference-wav "C:\CHEMIN_PRIVE\reference_15s.wav" --output "$env:LOCALAPPDATA\ATLAS\private\pocket\voice_french.safetensors" --allow-initial-download
~~~

La commande ne doit pas être lancée avant qualification du script sur Windows. L'accès au modèle Kyutai permettant le clonage vocal nécessite que le compte Hugging Face ait personnellement accepté les conditions et soit authentifié sur le GTR7 ; l'autorisation d'utiliser les enregistrements dans ATLAS a déjà été accordée.

## Comportement du script

- Vérifie les chemins absolus, le binaire version 3.3.0, le WAV mono PCM16, une durée de 5 à 30 secondes et un signal non silencieux.
- Refuse les dossiers situés dans un dépôt Git, les profils existants et les sorties via lien symbolique.
- Sans --allow-initial-download, bloque l'endpoint HF distant. Avec cette option, seul l'export initial tente d'obtenir les poids autorisés, avec le compte connecté ; aucun WAV privé n'est téléchargé vers le cloud par le script.
- Vérifie ensuite une génération réelle depuis le profil exporté avec HF_ENDPOINT local inaccessible ; inspecte le WAV (format, durée et signal).
- Publie le profil final de façon atomique uniquement après réussite, sans écraser un profil existant ; nettoie les fichiers temporaires.
- Capture les sorties de Pocket TTS sans afficher les chemins personnels ni le token.

Chaque composant des chemins sensibles est contrôlé avant résolution et aux
points de création/publication. Les liens symboliques, jonctions et autres
reparse points Windows sont refusés, même dans un dossier ancêtre. Les chemins
réseau Windows sont également refusés. Ces contrôles ne remplacent pas les ACL
privées du compte ni la protection du PC contre un processus malveillant ayant
les mêmes droits qui modifierait simultanément le système de fichiers.

Le WAV de contrôle est supprimé avant publication du profil final. Lors d'un
échec, chaque temporaire appartenant à la tentative fait l'objet d'un nettoyage
indépendant. Une suppression refusée ne masque pas l'erreur principale : les
catégories de temporaires conservés sont signalées sans chemin ni contenu
privé. Aucun fichier préexistant n'est supprimé pour réparer un échec. Un
verrouillage persistant peut nécessiter un nettoyage local ultérieur ; le
programme ne prétend pas avoir effacé un fichier qu'il n'a pas pu supprimer.

Les tests Python du script utilisent seulement des WAV et des poids fictifs. Ils vérifient les contrats techniques, la confidentialité des sorties, le refus d'écrasement, la suppression en cas d'échec, le respect du hors ligne et le refus d'export dans Git.

## Non validé à ce stade

L'accès effectif aux poids français avec clonage depuis le GTR7, la création du profil privé, la fidélité du timbre et la latence restent NON VÉRIFIÉS. Piper reste le moteur par défaut et aucune configuration personnelle du GTR7 n'est modifiée par cette PR.

Il est interdit de committer un WAV de Rachid, une empreinte vocale, un profil safetensors ou un identifiant de Hugging Face.


## Simplification : lanceur Windows sans chemins à saisir

Une fois la CI validée, un **paquet privé hors GitHub** pourra contenir uniquement :
- la référence WAV de Rachid déjà fournie (15 secondes), jamais committée ;
- `scripts/prepare_pocket_voice.py` et `scripts/atlas_voice_setup.py` ;
- `PREPARER_MA_VOIX_ATLAS.cmd` et une courte notice.

Il suffira de décompresser le paquet sur le GTR7 et de double-cliquer sur `PREPARER_MA_VOIX_ATLAS.cmd`. Le lanceur vérifie la présence de Python, télécharge **uniquement** l'archive officielle Kyutai depuis GitHub, vérifie le SHA-256 connu, extrait le binaire dans `%LOCALAPPDATA%\ATLAS\private\pocket\engine` puis crée un nouveau profil dans `%LOCALAPPDATA%\ATLAS\private\pocket\voice_french.safetensors`. Les chemins sont déterminés automatiquement ; aucun fichier préexistant n'est écrasé.

La **connexion au navigateur Hugging Face n'est pas automatiquement une connexion pour le binaire Rust**. Si aucun jeton local de lecture n'est disponible, le lanceur demandera de saisir un token Hugging Face **uniquement dans la console locale**, saisie masquée. Le token n'est pas sauvegardé dans un fichier ATLAS ni affiché dans les logs. Il n'est transmis qu'au client Hugging Face officiel pour récupérer les poids de clonage autorisés. Aucun token ne doit être transmis par chat.

Ce lanceur et sa procédure sont couverts par `tests/test_atlas_voice_setup.py` avec des archives, fichiers et tokens simulés. Ils n'exécutent ni vrai clonage, ni traitement de la voix personnelle sur GitHub Actions.

Les cas Windows comprennent le lancement réel du `.cmd` depuis des paquets
synthétiques imbriqués et plats, avec codes de sortie Python 0 et 7, ainsi que
le refus d'un paquet sans script. Le code de sortie est conservé après la pause
du lanceur. Les tests natifs créent des jonctions, un verrou sans partage de
suppression, un fichier en lecture seule et un refus d'écriture par ACL, puis
restaurent les ressources de test. Aucun de ces tests ne constitue un clonage
personnel. Leurs résultats doivent être vérifiés sur Windows ; les exclusions
Windows sous Linux ne sont pas des validations de ces cas.

**Attention :** le paquet contenant la vraie voix est personnel et ne doit pas être diffusé ; la PR et GitHub CI n'en contiennent pas la moindre copie. La ressemblance et la latence restent à valider sur le GTR7 après création réelle du profil. Piper demeure le moteur actif tant que cette vérification n'a pas été faite.
